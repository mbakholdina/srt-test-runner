import configparser
import logging
import pathlib
import signal
import subprocess
import sys
import time
import typing


import attr
import click


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)-15s [%(levelname)s] %(message)s',
)
logger = logging.getLogger(__name__)


SSH_CONNECTION_TIMEOUT = 10
# NOTE: It is important to add "-t" option in order for SSH 
# to transfer SIGINT, SIGTERM signals to the command
# NOTE: It is important to add "-o BatchMode=yes" option 
# in order to disable any kind of promt
# NOTE: It is important to add # "-o ConnectTimeout={SSH_CONNECTION_TIMEOUT}"
# option in case when the server is down not to wait and be able to check 
# quickly that the process has not been started successfully
SSH_COMMON_ARGS = [
    'ssh', 
    '-t',
    '-o', 'BatchMode=yes',
    '-o', f'ConnectTimeout={SSH_CONNECTION_TIMEOUT}',
]


class ProcessHasNotBeenCreated(Exception):
    pass

class ProcessHasNotBeenStartedSuccessfully(Exception):
    pass

class ProcessHasNotBeenKilled(Exception):
    pass


def process_is_running(process):
    """ 
    Returns:
        A tuple of (result, returncode) where 
        - is_running is equal to True if the process is running and False if
        the process has terminated,
        - returncode is None if the process is running and the actual value 
        of returncode if the process has terminated.
    """
    is_running = True
    returncode = process.poll()
    if returncode is not None:
        is_running = False
    return (is_running, returncode)

def create_process(name, args, via_ssh: bool=False):
    """ 
    name: name of the application being started
    args: process args

    Raises:
        ProcessHasNotBeenCreated
        ProcessHasNotBeenStarted
    """

    try:
        logger.debug('Starting process: {}'.format(name))
        if sys.platform == 'win32':
            process = subprocess.Popen(
                args, 
                stdin =subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=False,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                bufsize=1
            )
        else:
            process = subprocess.Popen(
                args, 
                #stdin =subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                #universal_newlines=False,
                bufsize=1
            )
    except OSError as e:
        raise ProcessHasNotBeenCreated('{}. Error: {}'.format(name, e))

    # Check that the process has started successfully and has not terminated
    # because of an error
    if via_ssh:
        time.sleep(SSH_CONNECTION_TIMEOUT + 1)
    else:
        time.sleep(1)
    logger.debug('Checking that the process has started successfully: {}'.format(name))
    is_running, returncode = process_is_running(process)
    if not is_running:
        raise ProcessHasNotBeenStartedSuccessfully(
            "{}, returncode {}, stderr: {}".format(name, returncode, process.stderr.readlines())
        )

    logger.debug('Started successfully')
    return process

def cleanup_process(process_tuple):
    """ 
    Clean up actions for the process. 

    Raises:
        ProcessHasNotBeenKilled
    """
    name, process = process_tuple
    # NOTE: There is a problem with terminating processes which use SSH 
    # to run a command on a remote server. The problem is in SSH not 
    # forwarding a signal (e.g., SIGINT, SIGTERM). As a result, SSH session 
    # itself terminates and process.poll() returns None, however 
    # an application started from a command continues to work on a remote server.
    # The solution is to use -t option in order to allocate a pseudo-terminal. 
    # See https://stackoverflow.com/questions/48419781/work-around-ssh-does-not-forward-signal
    # for details. FIXME: Maybe it is reasonable to add additional check in
    # clean-up actions that the process is not running on a remote server
    # ps -A | grep [process_name]

    # FIXME: However, there is a problem with wrong interpretation of carriage 
    # (\r\n) from pseudo-terminal in this case. Check stdout, it is full of b'\r\n'.

    # FIXME: Signals may not work on Windows properly. Might be useful
    # https://stefan.sofa-rockers.org/2013/08/15/handling-sub-process-hierarchies-python-linux-os-x/

    is_running, _ = process_is_running(process)
    if not is_running: 
        logger.info(f'Process {name} is not running, no need to terminate')
        return
    
    logger.info(f'Terminating {name}')
    # logger.info('OS: {}'.format(sys.platform))
    sig = signal.CTRL_C_EVENT if sys.platform == 'win32' else signal.SIGINT
    process.send_signal(sig)
    for i in range(3):
        time.sleep(1)
        is_running, _ = process_is_running(process)
        if not is_running: 
            logger.info('Terminated')
            return

    # TODO: (For future) Experiment with this more. If stransmit will not 
    # stop after several terminations, there is a problem, and kill() will
    # hide this problem in this case.
    
    # TODO: (!) There is a problem with tsp, it's actually not killed
    # however process_is_running(process) becomes False
    is_running, _ = process_is_running(process)
    if is_running:
        logger.info(f'Killing {name}')
        process.kill()
        time.sleep(1)
    is_running, _ = process_is_running(process)
    if is_running:
        raise ProcessHasNotBeenKilled(f'{name}, id: {process.pid}')
    logger.info('Killed')

def start_tshark(
    interface, 
    port, 
    file_info,
    start_via_ssh: bool=False,
    ssh_username: typing.Optional[str]=None,
    ssh_host: typing.Optional[str]=None
):
    logger.info('Starting tshark on a local machine')
    process_name = 'tshark'

    args = []
    if start_via_ssh:
        args += SSH_COMMON_ARGS
        args += [f'{ssh_username}@{ssh_host}']

    scenario, algdesc, bitrate = file_info
    filename = scenario + "-alg-{}-blt-{}bps-snd.pcapng".format(algdesc, bitrate)
    args += [
        'tshark', 
        '-i', interface, 
        '-f', 'udp port {}'.format(port), 
        '-s', '1500', 
        '-w', filename
    ]
    process = create_process(process_name, args)
    logger.info('Started successfully')
    return (process_name, process)

def start_sender(
    snd_path_to_srt,
    dst_host,
    dst_port,
    params,
    collect_stats: bool=False,
    file_info=None,
    sender_number=None
):
    name = f'srt sender {sender_number}'
    logger.info(f'Starting {name} on a local machine')

    bitrate, repeat, maxbw = params
    args = []
    args += [
        f'{snd_path_to_srt}/srt-test-messaging', 
        f'srt://{dst_host}:{dst_port}?sndbuf=12058624&smoother=live&maxbw={maxbw}&nakreport=true',
        "",
        '-msgsize', '1456',
        '-reply', '0', 
        '-printmsg', '0',
        '-bitrate', str(bitrate), 
        '-repeat', str(repeat),
    ]
    if collect_stats:
        scenario, algdescr, bitrate = file_info
        # FIXME: Create results folder automatically
        stats_file = f'_results/{scenario}-alg-{algdescr}-blt-{bitrate}bps-stats-snd-{sender_number}.csv'
        args += [
            '-statsfreq', '1',
            '-statsfile', stats_file,
        ]
        
    snd_srt_process = create_process(name, args)
    logger.info('Started successfully')
    return (name, snd_srt_process)

def start_receiver(
    rcv_ssh_host, 
    rcv_ssh_username, 
    rcv_path_to_srt, 
    dst_port,
    collect_stats: bool=False,
    file_info=None
):
    # FIXME: maxcon=50 is hard-coded for now
    name = 'srt receiver'
    logger.info(f'Starting {name} on a remote machine: {rcv_ssh_host}')
    args = []
    args += SSH_COMMON_ARGS
    args += [
        f'{rcv_ssh_username}@{rcv_ssh_host}',
        f'{rcv_path_to_srt}/srt-test-messaging',
        f'"srt://:{dst_port}?rcvbuf=12058624&smoother=live&maxcon=50&nakreport=true"',
        '-msgsize', '1456',
        '-reply', '0', 
        '-printmsg', '0'
    ]
    if collect_stats:
        args += ['-statsfreq', '1']
        scenario, algdescr, bitrate = file_info
        # FIXME: Create results folder automatically
        stats_file = f'_results/{scenario}-alg-{algdescr}-blt-{bitrate}bps-stats-rcv.csv'
        args += ['-statsfile', stats_file]
    print(args)
    process = create_process(name, args, True)
    logger.info('Started successfully')
    return (name, process)

@attr.s
class Config:
    """
    Global configuration settings.
    """
    rcv_ssh_host: str = attr.ib()
    rcv_ssh_username: str = attr.ib()
    rcv_path_to_srt: str = attr.ib()
    snd_path_to_srt: str = attr.ib()
    snd_tshark_iface: str = attr.ib()
    dst_host: str = attr.ib()
    dst_port: str = attr.ib()
    algdescr: str = attr.ib()
    scenario: str = attr.ib()
    bitrate_min: int = attr.ib()
    bitrate_max: int = attr.ib()
    bitrate_step: int = attr.ib()
    time_to_stream: int = attr.ib()

    @classmethod
    def from_config_filepath(cls, config_filepath: pathlib.Path):
        parsed_config = configparser.ConfigParser()
        with config_filepath.open('r', encoding='utf-8') as fp:
            parsed_config.read_file(fp)
        return cls(
            parsed_config['receiver']['rcv_ssh_host'],
            parsed_config['receiver']['rcv_ssh_username'],
            parsed_config['receiver']['rcv_path_to_srt'],
            parsed_config['sender']['snd_path_to_srt'],
            parsed_config['sender']['snd_tshark_iface'],
            parsed_config['bw-loop-test']['dst_host'],
            parsed_config['bw-loop-test']['dst_port'],
            parsed_config['bw-loop-test']['algdescr'],
            parsed_config['bw-loop-test']['scenario'],
            int(parsed_config['bw-loop-test']['bitrate_min']),
            int(parsed_config['bw-loop-test']['bitrate_max']),
            int(parsed_config['bw-loop-test']['bitrate_step']),
            int(parsed_config['bw-loop-test']['time_to_stream'])
        )

# def for_one_sender():
#     for bitrate in range(config.bitrate_min, config.bitrate_max, config.bitrate_step):
#         # Information needed to form .csv stats and .pcapng WireShark
#         # files' names
#         file_info = (config.scenario, config.algdescr, bitrate)

#         # Starting SRT on a receiver side
#         if rcv == 'remotely':
#             rcv_srt_process = start_receiver(
#                 config.rcv_ssh_host, 
#                 config.rcv_ssh_username, 
#                 config.rcv_path_to_srt, 
#                 config.dst_port,
#                 collect_stats,
#                 file_info
#             )
#             processes.append(rcv_srt_process)
#             time.sleep(3)

#         # Starting tshark on a sender side
#         if run_tshark:
#             snd_tshark_process = start_tshark(
#                 config.snd_tshark_iface, 
#                 config.dst_port, 
#                 file_info
#             )
#             processes.append(snd_tshark_process)
#             time.sleep(3)

#         # Calculate number of packets for 20 sec of streaming
#         # based on the target bitrate and packet size
#         repeat = 20 * bitrate // (1456 * 8)
#         maxbw  = int(bitrate // 8 * 1.25)
#         params = (bitrate, repeat, maxbw)

#         # Starting SRT on a sender side
#         logger.info("Starting streaming with bitrate {}, repeat {}".format(bitrate, repeat))
#         snd_srt_process = start_sender(
#             config.snd_path_to_srt,
#             config.dst_host,
#             config.dst_port,
#             params,
#             collect_stats,
#             file_info
#         )
#         processes.append(snd_srt_process)

#         # Check available bandwidth
#         sleep_s = 20
#         is_running = True
#         i = 0
#         while is_running:
#             is_running, _ = process_is_running(snd_srt_process[1])
#             if is_running:
#                 time.sleep(sleep_s)
#                 # Next time sleep for 1 second to react on the process finished
#                 sleep_s = 1
#                 i += 1

#         logger.info('Done')
#         time.sleep(3)

#         if run_tshark:
#             cleanup_process(snd_tshark_process)
#             time.sleep(3)
#         if rcv == 'remotely':
#             cleanup_process(rcv_srt_process)
#             time.sleep(3)

#         if i >= 5:
#             logger.info("Waited {} seconds. {} is considered as max BW".format(20 + i, bitrate))
#             break

def start_several_senders(
    config,
    bitrate,
    number_of_senders,
    collect_stats,
    file_info
):
    # Calculate number of packets for time_to_stream sec of streaming
    # based on the target bitrate and packet size
    repeat = config.time_to_stream * bitrate // (1456 * 8)
    maxbw  = int(bitrate // 8 * 1.25)
    params = (bitrate, repeat, maxbw)

    logger.info(
        f'Starting streaming with bitrate {bitrate}, repeat {repeat}, '
        f'senders {number_of_senders}'
    )

    sender_processes = []

    for i in range(0, number_of_senders):
        snd_srt_process = start_sender(
            config.snd_path_to_srt,
            config.dst_host,
            config.dst_port,
            params,
            collect_stats,
            file_info,
            i
        )
        sender_processes.append(snd_srt_process)

    # print(sender_processes)
    return sender_processes

def calculate_extra_time(sender_processes):
    extra_time = 0
    for process_tuple in sender_processes:
        # print(process_tuple)
        is_running = True
        _, process = process_tuple
        while is_running:
            is_running, _ = process_is_running(process)
            if is_running:
                # print('still running')
                time.sleep(1)
                extra_time += 1
                # print(extra_time)

    logger.info(f'Extra time spent on streaming: {extra_time}')
    return extra_time


@click.command()
@click.argument(
    'config_filepath', 
    type=click.Path(exists=True)
)
@click.option(
    '--rcv', 
    type=click.Choice(['manually', 'remotely']), 
    help=	'Start a receiver manually or remotely via SSH. In case of '
            'manual receiver start, please do not forget to do it '
            'before running the script.',
    required=True
)
@click.option(
    '--number-of-senders', 
    default=1,
    help=   'Number of senders to start.',
    show_default=True
)
@click.option(
    '--collect-stats', 
    is_flag=True, 
    help='Collect SRT statistics.'
)
@click.option(
    '--run-tshark',
    is_flag=True,
    help='Run tshark.'
)
def main(
    config_filepath,
    rcv,
    number_of_senders,
    collect_stats,
    run_tshark
):
    config = Config.from_config_filepath(pathlib.Path(config_filepath))

    processes = []
    try:
        for bitrate in range(config.bitrate_min, config.bitrate_max, config.bitrate_step):
            # Information needed to form .csv stats and .pcapng WireShark
            # files' names
            file_info = (config.scenario, config.algdescr, bitrate)

            # Starting SRT on a receiver side
            if rcv == 'remotely':
                rcv_srt_process = start_receiver(
                    config.rcv_ssh_host, 
                    config.rcv_ssh_username, 
                    config.rcv_path_to_srt, 
                    config.dst_port,
                    collect_stats,
                    file_info
                )
                processes.append(rcv_srt_process)
                time.sleep(3)

            # Starting tshark on a sender side
            if run_tshark:
                snd_tshark_process = start_tshark(
                    config.snd_tshark_iface, 
                    config.dst_port, 
                    file_info
                )
                processes.append(snd_tshark_process)
                time.sleep(3)

            # Starting several SRT senders on a sender side to stream for
            # config.time_to_stream seconds
            sender_processes = start_several_senders(
                config,
                bitrate,
                number_of_senders,
                collect_stats,
                file_info
            )
            for p in sender_processes:
                processes.append(p)

            # Sleep for config.time_to_stream seconds to wait while senders 
            # will finish the streaming and then check how many senders are 
            # still running.
            time.sleep(config.time_to_stream)
            extra_time = calculate_extra_time(sender_processes)

            logger.info('Done')
            time.sleep(3)

            if run_tshark:
                cleanup_process(snd_tshark_process)
                time.sleep(3)
            if rcv == 'remotely':
                cleanup_process(rcv_srt_process)
                time.sleep(3)

            if extra_time >= 5:
                logger.info(
                    f'Waited {config.time_to_stream + extra_time} seconds '
                    f'instead of {config.time_to_stream}. '
                    f'{bitrate}bps is considered as maximim available bandwidth.'
                )
                break
    except KeyboardInterrupt:
        logger.info('KeyboardInterrupt has been caught')
    except (
        ProcessHasNotBeenCreated,
        ProcessHasNotBeenStartedSuccessfully,
        ProcessHasNotBeenKilled,
    ) as error:
        logger.info(
            f'Exception occured ({error.__class__.__name__}): {error}'
        )
    finally:
        logger.info('Cleaning up')
        # print(processes)

        if len(processes) == 0:
            logger.info('Nothing to clean up')
            return

        for process_tuple in reversed(processes):
            try:
                # print(process_tuple)
                cleanup_process(process_tuple)
            except (ProcessHasNotBeenKilled) as error:
                # TODO: Collect the information regarding non killed processes
                # and perfom additional clean-up actions
                logger.info(
                    f'During cleaning up exception occured '
                    f'({error.__class__.__name__}): {error}. The next '
                    f'experiment can not be done further!'
                )


if __name__ == '__main__':
    main()