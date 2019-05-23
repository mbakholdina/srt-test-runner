import logging
import signal
import subprocess
import sys
import time
import typing


# TODO:     Improve documentation


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
DELIMETER = 1000000


class ProcessHasNotBeenCreated(Exception):
    pass

class ProcessHasNotBeenStartedSuccessfully(Exception):
    pass

class ProcessHasNotBeenKilled(Exception):
    pass

class ParallelSendersExecutionFailed(Exception):
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
        logger.debug(f'Starting process: {name}')
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
        raise ProcessHasNotBeenCreated(f'{name}. Error: {e}')

    # Check that the process has started successfully and has not terminated
    # because of an error
    if via_ssh:
        time.sleep(SSH_CONNECTION_TIMEOUT + 1)
    else:
        time.sleep(1)
    logger.debug(f'Checking that the process has started successfully: {name}')
    is_running, returncode = process_is_running(process)
    if not is_running:
        raise ProcessHasNotBeenStartedSuccessfully(
            f'{name}, returncode {returncode}, stderr: {process.stderr.readlines()}'
        )

    logger.debug(f'Started successfully: {name}')
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
        logger.info(
            f'Process is not running, no need to terminate: {process_tuple}'
        )
        return
    
    logger.info(f'Terminating: {process_tuple}')
    # logger.info('OS: {}'.format(sys.platform))
    sig = signal.CTRL_C_EVENT if sys.platform == 'win32' else signal.SIGINT
    process.send_signal(sig)
    for i in range(3):
        time.sleep(1)
        is_running, _ = process_is_running(process)
        if not is_running: 
            logger.info(f'Terminated: {process_tuple}')
            return

    # TODO: (For future) Experiment with this more. If stransmit will not 
    # stop after several terminations, there is a problem, and kill() will
    # hide this problem in this case.
    
    # TODO: (!) There is a problem with tsp, it's actually not killed
    # however process_is_running(process) becomes False
    is_running, _ = process_is_running(process)
    if is_running:
        logger.info(f'Killing: {process_tuple}')
        process.kill()
        time.sleep(1)
    is_running, _ = process_is_running(process)
    if is_running:
        raise ProcessHasNotBeenKilled(f'{name}, id: {process.pid}')
    logger.info(f'Killed: {process_tuple}')


def start_tshark(
    interface, 
    port, 
    filename: str,
    results_dir: str,
    start_via_ssh: bool=False,
    ssh_username: typing.Optional[str]=None,
    ssh_host: typing.Optional[str]=None
):
    name = 'tshark'
    logger.info('Starting on a local machine: {name}')

    args = []
    if start_via_ssh:
        args += SSH_COMMON_ARGS
        args += [f'{ssh_username}@{ssh_host}']

    filepath = results_dir / filename
    args += [
        'tshark', 
        '-i', interface, 
        '-f', f'udp port {port}', 
        '-s', '1500', 
        '-w', filepath
    ]
    process = create_process(name, args)
    logger.info('Started successfully: {name}')
    return (name, process)

def calculate_extra_time(sender_processes):
    """ 
    Calculate extra time needed for senders to fininsh streaming.

    Attributes:
        sender_processes: List of processes tuples. 
    """
    extra_time = 0
    for process_tuple in sender_processes:
        is_running = True
        _, process = process_tuple
        while is_running:
            is_running, _ = process_is_running(process)
            if is_running:
                time.sleep(1)
                extra_time += 1

    # logger.info(f'Extra time spent on streaming: {extra_time}')
    return extra_time