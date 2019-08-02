from abc import abstractmethod, ABC
import enum
import logging
import pprint
import time

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


### IObject (application, hublet, etc.) ###
# ? IObjectConfig

class IObject(ABC):
    @classmethod
    @abstractmethod
    def from_config(cls, config: dict):
        pass

    @abstractmethod
    def make_args(self):
        pass


class Tshark(IObject):

    def __init__(self, interface: str, port: str, results_dir: str, filename: str):
        self.name = 'tshark'
        self.interface = interface
        self.port = port
        # TODO: pathlib.Path
        self.results_dir = results_dir
        self.filename = filename

    @classmethod
    def from_config(cls, config: dict):
        # config - object config (parameters needed to form the args for cmd)
        """ 
        config = {
            'interface': 'en0',
            'port': 4200,
            'results_dir': '_results',
            'filename': 'tshark.pcapng',
        }
        """
        return cls(
            config['interface'],
            config['port'],
            config['results_dir'],
            config['filename']
        )

    def make_args(self):
        # TODO: Convert to pathlib.Path
        # filepath = self.results_dir / self.filename
        filepath = self.results_dir + '/' + self.filename
        return [
            'tshark', 
            '-i', self.interface, 
            '-f', f'udp port {self.port}', 
            '-s', '1500', 
            '-w', filepath
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
        results_dir
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
        results_dir: pathlib.Path=None
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
        self.results_dir = results_dir

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
            'results_dir': '_results',
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
            config['results_dir']
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
            # stats_file = self.results_dir / f'{self.description}-stats-{self.type}.csv'
            stats_file = self.results_dir + '/' + f'{self.description}-stats-{self.type}.csv'
            args += [
                '-statsfreq', '1',
                '-statsfile', stats_file,
            ]
        
        return args


### IRunner (as of now, IProcess) - process, thread, etc.

class IRunner(ABC):
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


class SubProcess(IRunner):

    def __init__(self, obj):
        self.obj = obj
        self.process = None

    @classmethod
    def from_config(cls, obj: IObject, config: dict=None):
        return cls(obj)

    def start(self):
        logger.info(f'Starting on-premises: {self.obj.name}')
        self.process = shared.create_process(self.obj.name, self.obj.make_args())
        logger.info(f'Started successfully: {self.obj.name}, {self.process}')

    def stop(self):
        # TODO: use get_status method in order to check whether the process is running or not
        # instead of currently implemented logic in cleanup_process
        # TODO: change cleanup function to have only one input - process
        logger.info(f'Stopping on-premises: {self.obj.name}, {self.process}')
        shared.cleanup_process((self.obj.name, self.process))
        logger.info(f'Stopped successfully: {self.obj.name}, {self.process}')

    def get_status(self):
        # TODO: Adapt process_is_running()
        is_running, returncode = shared.process_is_running(self.process)
        return is_running


class SSHSubProcess(IRunner):

    def __init__(self, obj, username, host):
        self.obj = obj
        self.username = username
        self.host = host
        self.process = None

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
        args = []
        args += shared.SSH_COMMON_ARGS
        args += [f'{self.username}@{self.host}']
        obj_args = [f'"{arg}"'for arg in self.obj.make_args()]
        args += obj_args
        # print(args)
        self.process = shared.create_process(self.obj.name, args, True)
        logger.info(f'Started successfully: {self.obj.name}, {self.process}')

    def stop(self):
        # TODO: use get_status method in order to check whether the process is running or not
        # instead of currently implemented logic in cleanup_process
        # TODO: change cleanup function to have only one input - process
        logger.info(f'Stopping on-premises: {self.obj.name}, {self.process}')
        shared.cleanup_process((self.obj.name, self.process))
        logger.info(f'Stopped successfully: {self.obj.name}, {self.process}')

    def get_status(self):
        # TODO: Adapt process_is_running()
        pass


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

    def create_runner(self, runner_type: str, obj, runner_config: dict) -> IRunner:
        runner = None

        if runner_type == 'subprocess':
            runner = SubProcess.from_config(obj, runner_config)
        elif runner_type == 'ssh-subprocess':
            runner = SSHSubProcess.from_config(obj, runner_config)
        else:
            print('No matching runner found')

        return runner


def create_task_config(obj_type, obj_config, runner_type, runner_config):
    return {
        'obj_type': obj_type,
        'obj_config': obj_config,
        'runner_type': runner_type,
        'runner_config': runner_config
    }


def create_experiment_config():
    config = {}
    tshark_config = {
        'interface': 'en0',
        'port': 4200,
        'results_dir': '_results',
        'filename': 'tshark.pcapng',
    }
    tshark_runner_config = None
    config['task1']= create_task_config('tshark', tshark_config, 'subprocess', tshark_runner_config)

    tshark_config = {
        'interface': 'eth0',
        'port': 4200,
        'results_dir': '_results',
        'filename': 'tshark.pcapng',
    }
    tshark_runner_config = {
        'username': 'msharabayko',
        'host': '65.52.227.197',
    }
    config['task2']= create_task_config('tshark', tshark_config, 'ssh-subprocess', tshark_runner_config)

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
        'results_dir': '_results',
    } 
    srt_test_msg_runner_config = None
    config['task3']= create_task_config('srt-test-messaging', srt_test_msg_config, 'subprocess', srt_test_msg_runner_config)

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
        'results_dir': '_results',
    }
    srt_test_msg_runner_config = {
        'username': 'msharabayko',
        'host': '65.52.227.197',
    }
    config['task4']= create_task_config('srt-test-messaging', srt_test_msg_config, 'ssh-subprocess', srt_test_msg_runner_config)

    pp = pprint.PrettyPrinter(indent=2)
    pp.pprint(config)

    return config


if __name__ == '__main__':

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)-15s [%(levelname)s] %(message)s',
    )

    factory = SimpleFactory()
    config = create_experiment_config()

    for task, task_config in config.items():
        obj = factory.create_object(task_config['obj_type'], task_config['obj_config'])
        obj_runner = factory.create_runner(task_config['runner_type'], obj, task_config['runner_config'])
        obj_runner.start()
        time.sleep(10)
        obj_runner.stop()
        time.sleep(5)