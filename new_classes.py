from abc import abstractmethod, ABC
import enum
import logging
import pathlib
import pprint
import time

import fabric
import paramiko

import shared


logger = logging.getLogger(__name__)


@enum.unique
class SrtApplicationType(enum.Enum):
    """
    Defines the type of the application supporting SRT protocol in a
    a particular experiment. Affects arguments generation and stats
    filename.
    """
    #:
    sender = "snd"
    #:
    receiver = "rcv"
    #:
    forwarder = "fwd"


def get_query(attrs_values):
    query_elements = []
    for attr, value in attrs_values:
        query_elements.append(f'{attr}={value}')
    return f'{"&".join(query_elements)}'


class DirectoryHasNotBeenCreated(Exception):
    pass

class ProcessHasBeenStartedAlready(Exception):
    pass


### IObject (application, hublet, etc.) ###
# ? IObjectConfig

class IObject(ABC):
    # ??? Name, dirpath=None, filepath=None - obligitary attributes
    # I work with this attrs in IRunner
    # ??? Is this a good approach

    @classmethod
    @abstractmethod
    def from_config(cls, config: dict):
        pass

    @abstractmethod
    def make_args(self):
        pass


class Tshark(IObject):

    def __init__(self, interface: str, port: str, filename: str, dirpath: str):
        # if the object assumes to produce some output like dump files, stats files,
        # dirpath should be specified
        # TODO: Make dirpath optional, make check that dirpath != None and 
        # only then add -w option
        self.name = 'tshark'
        self.interface = interface
        self.port = port
        self.filename = filename
        # TODO: pathlib.Path
        self.dirpath = dirpath
        # TODO: Convert to pathlib.Path
        # filepath = self.dirpath / self.filename
        # ? property
        self.filepath = self.dirpath + '/' + self.filename + '.pcapng'

    @classmethod
    def from_config(cls, config: dict):
        # config - object config (parameters needed to form the args for cmd)
        """ 
        config = {
            'interface': 'en0',
            'port': 4200,
            'filename': 'tshark_dump',
            'dirpath': '_results',
        }
        """
        return cls(
            config['interface'],
            config['port'],
            config['filename'],
            config['dirpath']
        )

    def make_args(self):
        return [
            'tshark', 
            '-i', self.interface, 
            '-f', f'udp port {self.port}', 
            '-s', '1500', 
            '-w', self.filepath
        ]


class SrtTestMessaging(IObject):

    def __init__(
        self,
        type,
        path,
        host,
        port,
        attrs_values,
        options_values,
        collect_stats,
        description,
        dirpath
    ):
        """
        Types:
        number,
        path_to_srt: str,
        host: str,
        port: str,
        attrs_values: typing.Optional[typing.List[typing.Tuple[str, str]]]=None,
        options_values: typing.Optional[typing.List[typing.Tuple[str, str]]]=None,
        description: str=None,
        collect_stats: bool=False,
        dirpath: pathlib.Path=None
        """
        self.name = 'srt-test-messaging'
        self.type = type
        self.path = path
        self.host = host
        self.port = port
        self.attrs_values = attrs_values
        self.options_values = options_values
        self.collect_stats = collect_stats
        self.description = description
        self.dirpath = dirpath
        # TODO: Determine
        self.filepath = None

    @classmethod
    def from_config(cls, config: dict):
        """
        config = {
            'path': '/Users/msharabayko/projects/srt/srt-maxlovic/_build',
            'type': 'snd',
            'host': '137.135.161.223',
            'port': '4200',
            'attrs_values': [
                ('rcvbuf', '12058624'),
                ('congestion', 'live'),
                ('maxcon', '50'),
            ],
            'options_values': [
                ('-msgsize', '1456'),
                ('-reply', '0'),
                ('-printmsg', '0'),
            ],
            'collect_stats': True,
            'description': 'busy_waiting',
            'dirpath': '_results',
        } 

        attrs_values:
            A list of SRT options (SRT URI attributes) in a format
            [('rcvbuf', '12058624'), ('smoother', 'live'), ('maxcon', '50')].
        options_values:
            A list of srt-test-messaging application options in a format
            [('-msgsize', '1456'), ('-reply', '0'), ('-printmsg', '0')].
        """
        return cls(
            config['type'],
            config['path'],
            config['host'],
            config['port'],
            config['attrs_values'],
            config['options_values'],
            config['collect_stats'],
            config['description'],
            config['dirpath']
        )

    def make_args(self):
        # TODO: Add receiver support
        args = []
        args += [f'{self.path}/{self.name}']

        if self.attrs_values is not None:
            # FIXME: But here there is a problem with "" because sender has been
            # started locally, not via SSH
            if self.type == SrtApplicationType.sender.value:
                args += [f'srt://{self.host}:{self.port}?{get_query(self.attrs_values)}']
            # FIXME: Deleted additonal quotes, needs to be tested with receiver running locally
            if self.type == SrtApplicationType.receiver.value:
                args += [f'srt://{self.host}:{self.port}?{get_query(self.attrs_values)}']
        else:
            args += [f'srt://{self.host}:{self.port}']

        if self.type == SrtApplicationType.sender.value:
            args += ['']

        if self.options_values is not None:
            for option, value in self.options_values:
                args += [option, value]

        if self.collect_stats:
            # stats_file = self.dirpath / f'{self.description}-stats-{self.type}.csv'
            stats_file = self.dirpath + '/' + f'{self.description}-stats-{self.type}.csv'
            args += [
                '-statsfreq', '1',
                '-statsfile', stats_file,
            ]
        
        return args


### IRunner (as of now, IProcess) - process, thread, etc.
# ? IObjectRunner, ITaskRunner

class IRunner(ABC):
    @staticmethod
    @abstractmethod
    def _create_directory(dirpath: str):
        pass

    @classmethod
    @abstractmethod
    def from_config(cls, obj: IObject, config: dict):
        pass

    @abstractmethod
    def start(self):
        pass

    @abstractmethod
    def stop(self):
        pass

    @abstractmethod
    def get_status(self):
        pass

    @abstractmethod
    def collect_results(self):
        pass


class Subprocess(IRunner):

    def __init__(self, obj):
        self.obj = obj

        self.process = None
        self.is_started = False

    @staticmethod
    def _create_directory(dirpath: str):
        logger.info(f'Creating a directory for saving results: {dirpath}')
        dirpath = pathlib.Path(dirpath)
        if dirpath.exists():
            # shutil.rmtree(dirpath)
            logger.info('Already exists')
            return
        dirpath.mkdir(parents=True)
        logger.info('Created successfully')

    @classmethod
    def from_config(cls, obj: IObject, config: dict=None):
        return cls(obj)

    def start(self):
        logger.info(f'Starting on-premises: {self.obj.name}')

        if self.is_started:
            raise ValueError(f'Process has been started already: {self.obj.name}, {self.process}')

        if self.obj.dirpath != None:
            self._create_directory(self.obj.dirpath)

        # TODO: Try, except + rename to start_subprocess + rename exceptions inside
        self.process = shared.create_process(self.obj.name, self.obj.make_args())
        self.is_started = True

        logger.info(f'Started successfully: {self.obj.name}, {self.process}')

    def stop(self):
        # TODO: use get_status method in order to check whether the process is running or not
        # instead of currently implemented logic in cleanup_process
        # TODO: change cleanup function to have only one input - process
        logger.info(f'Stopping on-premises: {self.obj.name}, {self.process}')

        if not self.is_started:
            raise ValueError(f'Process has not been started yet: {self.obj.name}')

        shared.cleanup_process((self.obj.name, self.process))
        logger.info(f'Stopped successfully: {self.obj.name}, {self.process}')

    def get_status(self):
        # TODO: Adapt process_is_running()
        # is_running, returncode = shared.process_is_running(self.process)
        # return is_running
        pass

    def collect_results(self):
        logger.info('Collecting results')
        
        if not self.is_started:
            raise ValueError(f'Process has not been started yet: {self.obj.name}')

        logger.info('Not implemented')

        # TODO: Implement
        # exit code, stdout, stderr, files
        # download files via scp for SSHSubprocess


class SSHSubprocess(IRunner):

    def __init__(self, obj, username, host):
        self.obj = obj
        self.username = username
        self.host = host

        self.process = None
        self.is_started = False

    @staticmethod
    def _create_directory(dirpath: str, username: str, host: str):
        logger.info(f'Creating a directory for saving results: {dirpath}')

        try:
            # FIXME: By default Paramiko will attempt to connect to a running 
            # SSH agent (Unix style, e.g. a live SSH_AUTH_SOCK, or Pageant if 
            # one is on Windows). That's why promt for login-password is not 
            # disabled under condition that password is not configured via 
            # connect_kwargs.password
            with fabric.Connection(host=host, user=username) as c:
                # result = c.run(f'rm -rf {results_dir}')
                # if result.exited != 0:
                #     logger.info(f'Not created: {result}')
                #     return
                result = c.run(f'mkdir -p {dirpath}')
                # print(result.succeeded)
                # print(result.failed)
                # print(result.exited)
                # print(result)
                if result.exited != 0:
                    logger.debug(f'Directory has not been created: {dirpath}')
                    raise DirectoryHasNotBeenCreated(f'Username: {username}, host: {host}, dirpath: {dirpath}')
        except paramiko.ssh_exception.SSHException as error:
            logger.info(
                f'Exception occured ({error.__class__.__name__}): {error}. '
                'Check that the ssh-agent has been started.'
            )
            raise
        except TimeoutError as error:
            logger.info(
                f'Exception occured ({error.__class__.__name__}): {error}. '
                'Check that IP address of the remote machine is correct and the '
                'machine is not down.'
            )
            raise

        logger.info(f'Created successfully')

    @classmethod
    def from_config(cls, obj: IObject, config: dict):
        # obj - object (app, hublet) to run
        # config - runner config
        """
        config = {
            'username': 'msharabayko',
            'host': '137.135.161.223',
        }
        """
        return cls(obj, config['username'], config['host'])

    def start(self):
        logger.info(f'Starting remotely via SSH: {self.obj.name}')

        if self.is_started:
            raise ValueError(f'Process has been started already: {self.obj.name}, {self.process}')

        if self.obj.dirpath != None:
            self._create_directory(self.obj.dirpath, self.username, self.host)

        args = []
        args += shared.SSH_COMMON_ARGS
        args += [f'{self.username}@{self.host}']
        obj_args = [f'"{arg}"'for arg in self.obj.make_args()]
        args += obj_args
        
        self.process = shared.create_process(self.obj.name, args, True)
        self.is_started = True

        logger.info(f'Started successfully: {self.obj.name}, {self.process}')

    def stop(self):
        # TODO: use get_status method in order to check whether the process is running or not
        # instead of currently implemented logic in cleanup_process
        # TODO: change cleanup function to have only one input - process
        logger.info(f'Stopping remotely via SSH: {self.obj.name}, {self.process}')

        if not self.is_started:
            raise ValueError(f'Process has not been started yet: {self.obj.name}')

        shared.cleanup_process((self.obj.name, self.process))
        logger.info(f'Stopped successfully: {self.obj.name}, {self.process}')

    def get_status(self):
        # TODO: Adapt process_is_running()
        pass

    def collect_results(self):
        logger.info('Collecting results')
        
        if not self.is_started:
            raise ValueError(f'Process has not been started yet: {self.obj.name}')

        if self.obj.filepath is None:
            return

        with fabric.Connection(host=self.host, user=self.username) as c:
            result = c.get(self.obj.filepath)
            # TODO: Implement
            # http://docs.fabfile.org/en/1.14/api/core/operations.html
            # http://docs.fabfile.org/en/2.3/api/transfer.html
            
            # if result.exited != 0:
            #     logger.debug(f'Directory has not been created: {dirpath}')
            #     raise DirectoryHasNotBeenCreated(f'Username: {username}, host: {host}, dirpath: {dirpath}')

        # TODO: Implement
        # exit code, stdout, stderr, files
        # download files via scp for SSHSubprocess


### Simple Factory ###

class SimpleFactory:

    def create_object(self, obj_type: str, obj_config: dict) -> IObject:
        obj = None

        if obj_type == 'tshark':
            obj = Tshark.from_config(obj_config)
        elif obj_type == 'srt-test-messaging':
            obj = SrtTestMessaging.from_config(obj_config)
        else:
            print('No matching object found')

        return obj

    def create_runner(self, obj, runner_type: str, runner_config: dict) -> IRunner:
        runner = None

        if runner_type == 'subprocess':
            runner = Subprocess.from_config(obj, runner_config)
        elif runner_type == 'ssh-subprocess':
            runner = SSHSubprocess.from_config(obj, runner_config)
        else:
            print('No matching runner found')

        return runner


### Configs ###

def create_task_config(
    obj_type, 
    obj_config, 
    runner_type, 
    runner_config, 
    sleep_after_start: str=None, 
    sleep_after_stop: str=None,
    stop_order: int=None
):
    return {
        'obj_type': obj_type,
        'obj_config': obj_config,
        'runner_type': runner_type,
        'runner_config': runner_config,
        'sleep_after_start': sleep_after_start,
        'sleep_after_stop': sleep_after_stop,
        'stop_order': stop_order,
    }


def create_experiment_config(stop_after: int, ignore_stop_order: bool=True):
    dirpath = '_results'
    sleep_after_start = 3
    sleep_after_stop = 1

    config = {}
    config['stop_after'] = stop_after
    config['ignore_stop_order'] = ignore_stop_order

    config['tasks'] = {}
    tshark_config = {
        'interface': 'en0',
        'port': 4200,
        'filename': 'tshark_snd',
        'dirpath': '_results',
    }
    tshark_runner_config = None
    config['tasks']['0'] = create_task_config(
        'tshark', 
        tshark_config, 
        'subprocess', 
        tshark_runner_config,
        sleep_after_start
    )

    tshark_config = {
        'interface': 'eth0',
        'port': 4200,
        'filename': 'tshark_rcv',
        'dirpath': '_results_remote',
    }
    tshark_runner_config = {
        'username': 'msharabayko',
        'host': '137.135.164.27',
    }
    config['tasks']['1'] = create_task_config(
        'tshark', 
        tshark_config, 
        'ssh-subprocess', 
        tshark_runner_config,
        None,
        sleep_after_stop
    )

    srt_test_msg_config = {
        'path': '/Users/msharabayko/projects/srt/srt-maxlovic/_build',
        'type': 'rcv',
        'host': '',
        'port': '4200',
        'attrs_values': [
            ('rcvbuf', '12058624'),
            ('congestion', 'live'),
            ('maxcon', '50'),
        ],
        'options_values': [
            ('-msgsize', '1456'),
            ('-reply', '0'),
            ('-printmsg', '0'),
        ],
        'collect_stats': True,
        'description': 'busy_waiting',
        'dirpath': '_results',
    } 
    srt_test_msg_runner_config = None
    # config['task3']= create_task_config('srt-test-messaging', srt_test_msg_config, 'subprocess', srt_test_msg_runner_config)

    srt_test_msg_config = {
        'path': 'projects/srt-maxlovic/_build',
        'type': 'rcv',
        'host': '',
        'port': '4200',
        'attrs_values': [
            ('rcvbuf', '12058624'),
            ('congestion', 'live'),
            ('maxcon', '50'),
        ],
        'options_values': [
            ('-msgsize', '1456'),
            ('-reply', '0'),
            ('-printmsg', '0'),
        ],
        'collect_stats': True,
        'description': 'busy_waiting',
        'dirpath': '_results',
    }
    srt_test_msg_runner_config = {
        'username': 'msharabayko',
        'host': '65.52.227.197',
    }
    # config['task4']= create_task_config('srt-test-messaging', srt_test_msg_config, 'ssh-subprocess', srt_test_msg_runner_config)

    pp = pprint.PrettyPrinter(indent=2)
    pp.pprint(config)

    return config


### ITestRunner -> SingleExperimentRunner, TestRunner, CombinedTestRunner ###
# The methods will be similar to IRunner

class SingleExperimentRunner:

    def __init__(self, factory: SimpleFactory, config: dict):
        self.factory = factory
        self.config = config

        # TODO: Add attributes from config

        # TODO: Create a class for task: obj, obj_runner, sleep_after_stop, stop_order
        self.tasks = []
        self.is_started = False

    # TODO: create_directory

    def start(self):
        logger.info('[SingleExperimentRunner] Starting experiment')

        if self.is_started:
            raise ValueError(f'Experiment has been started already')

        for task, task_config in self.config['tasks'].items():
            obj = self.factory.create_object(task_config['obj_type'], task_config['obj_config'])
            obj_runner = self.factory.create_runner(obj, task_config['runner_type'], task_config['runner_config'])
            obj_runner.start()
            self.tasks += [(obj, obj_runner, task_config['sleep_after_stop'], task_config['stop_order'])]
            if task_config['sleep_after_start'] is not None:
                logger.info(f"[SingleExperimentRunner] Sleeping {task_config['sleep_after_start']} s")
                time.sleep(task_config['sleep_after_start'])

        self.is_started = True
            
    def stop(self):
        logger.info('[SingleExperimentRunner] Stopping experiment')

        if not self.is_started:
            raise ValueError(f'Experiment has not been started yet')

        # TODO: Stop the tasks in reverse order
        if self.config['ignore_stop_order']:
            for _, obj_runner, sleep_after_stop, _ in self.tasks:
                obj_runner.stop()
                if sleep_after_stop is not None:
                    logger.info(f"[SingleExperimentRunner] Sleeping {sleep_after_stop}s ...")
                    time.sleep(sleep_after_stop)

        # TODO: Implement stopping tasks according to the specified stop order

    def get_status(self):
        pass

    def collect_results(self):
        logger.info('[SingleExperimentRunner] Collecting experiment results')

        if not self.is_started:
            raise ValueError(f'Experiment has not been started yet')

        for _, obj_runner, _, _ in self.tasks:
            obj_runner.collect_results()


if __name__ == '__main__':

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)-15s [%(levelname)s] %(message)s',
    )

    factory = SimpleFactory()

    # time to stream
    stop_after = 20
    # This will be changed to loading the config from file
    # and then adjusting it (srt parameters, etc.) knowing what kind of
    # experiment we are going to do. Or we will provide a cli to user with
    # the list of parameters we need to know (or it would be just a file with the list of params),
    # and then config file for the experiment will be built in a function and parameters will be adjusted
    config = create_experiment_config(stop_after)

    exp_runner = SingleExperimentRunner(factory, config)
    exp_runner.start()
    logger.info(f'Sleeping {stop_after} s ...')
    time.sleep(stop_after)
    exp_runner.stop()
    exp_runner.collect_results()