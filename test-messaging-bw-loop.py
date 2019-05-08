import logging
import signal
import subprocess
import sys
import time


import click

# from threading import Thread


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)-15s [%(levelname)s] %(message)s',
)
logger = logging.getLogger(__name__)


SSH_CONNECTION_TIMEOUT = 10


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

def cleanup_process(name, process):
    """ 
    Clean up actions for the process. 

    Raises:
        ProcessHasNotBeenKilled
    """
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

    is_running, returncode = process_is_running(process)
    if not is_running: 
        logger.info(f'Process {name} is not running, no need to terminate')
        return
    
    logger.info(f'Terminating the process: {name}')
    # logger.info('OS: {}'.format(sys.platform))
    sig = signal.CTRL_C_EVENT if sys.platform == 'win32' else signal.SIGINT
    process.send_signal(sig)
    for i in range(3):
        time.sleep(1)
        is_running, returncode = process_is_running(process)
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
        logger.info(f'Killing the process: {name}')
        process.kill()
        time.sleep(1)
    is_running, _ = process_is_running(process)
    if is_running:
        raise ProcessHasNotBeenKilled(f'{name}, id: {process.pid}')
    logger.info('Killed')

def create_tshark(interface, port, output):
    args = ['tshark', '-i', interface, '-f', 'udp port {}'.format(port), '-s', '1500', '-w', output]
    return create_process("tshark", args)


@click.command()
@click.argument('rcv_ssh_host')
@click.argument('rcv_ssh_username')
@click.argument('dst_host')
@click.argument('dst_port')
# help='Algorithm description'
@click.argument('algdesc')
# help='File prefix - test scenario'
@click.argument('scenario')
# help='Network interface descriptor for tshark - eth0'
@click.argument('iface')
@click.option('--collect-stats', is_flag=True, help='Collect SRT statistics')
def main(
    rcv_ssh_host, 
    rcv_ssh_username, 
    dst_host, 
    dst_port, 
    algdesc, 
    scenario, 
    iface, 
    collect_stats
):
            
    rcv_path_to_srt = 'projects/srt/maxlovic'
    snd_path_to_srt = '.'

    processes = []
    try:
        logger.info(f'Starting srt receiver on a remote machine: {rcv_ssh_host}')
        # NOTE: It is important to add "-t" option in order for SSH 
        # to transfer SIGINT, SIGTERM signals to the command
        # NOTE: It is important to add "-o BatchMode=yes" option 
        # in order to disable any kind of promt
        # NOTE: It is important to add # "-o ConnectTimeout={SSH_CONNECTION_TIMEOUT}"
        # option in case when the server is down not to wait and be able to check 
        # quickly that the process has not been started successfully
        rcv_srt_args = [
            'ssh', 
            '-t',
            '-o', 'BatchMode=yes',
            '-o', f'ConnectTimeout={SSH_CONNECTION_TIMEOUT}',
            f'{rcv_ssh_username}@{rcv_ssh_host}',
            f'{rcv_path_to_srt}/srt-test-messaging',
            f'"srt://:{dst_port}?rcvbuf=12058624&smoother=live"',
            '-msgsize', '1456',
            '-reply', '0', 
            '-printmsg', '0'
        ]
        rcv_srt_process = create_process(
            'srt-test-messaging (rcv)', 
            rcv_srt_args, 
            True
        )
        processes.append(('srt-test-messaging (rcv)', rcv_srt_process))
        logger.info('Started successfully')

        logger.info('Starting streaming with different values of bitrate')

        # TODO: Add quotes to srt uri
        snd_common_srt_args = [
            f'{snd_path_to_srt}/srt-test-messaging', 
            f'srt://{dst_host}:{dst_port}?sndbuf=12058624&smoother=live',
            "",
            '-msgsize', '1456',
            '-reply', '0', 
            '-printmsg', '0'
        ]
        if collect_stats:
            snd_common_srt_args += ['-statsfreq', '1']


        # for bitrate in range(50000000, 1100000000, 50000000):
        for bitrate in range(5000000, 8000000, 1000000):
            # Calculate number of packets for 20 sec of streaming
            # based on the target bitrate and packet size.
            repeat = 20 * bitrate // (1456 * 8)
            maxbw  = int(bitrate // 8 * 1.25)

            pcapng_file = scenario + "-alg-{}-blt-{}bps.pcapng".format(algdesc, bitrate)
            tshark = create_tshark(
                interface=iface, 
                port=dst_port, 
                output=pcapng_file
            )
            processes.append(('tshark', tshark))
            time.sleep(3)

            args = snd_common_srt_args + ["-bitrate", str(bitrate), "-repeat", str(repeat)]
            if collect_stats:
                stats_file = scenario + "-alg-{}-blt-{}bps.csv".format(algdesc, bitrate)
                args += ['-statsfile', stats_file]
            args[1] += "&maxbw={}".format(maxbw)
            logger.info("Starting streaming with bitrate {}, repeat {}".format(bitrate, repeat))
            snd_srt_process = create_process('srt-test-messaging (snd)', args)
            processes.append(('srt-test-messaging (snd)', snd_srt_process))

            sleep_s = 20
            is_running = True
            i = 0
            while is_running:
                is_running, returncode = process_is_running(snd_srt_process)
                if is_running:
                    time.sleep(sleep_s)
                    sleep_s = 1  # Next time sleep for 1 second to react on the process finished.
                    i += 1

            logger.info("Done")
            time.sleep(3)
            cleanup_process("tshark", tshark)
            if i >= 5:
                logger.info("Waited {} seconds. {} is considered as max BW".format(20 + i, bitrate))
                break

        logger.info('Stopping srt receiver')
        time.sleep(3)
        cleanup_process('srt-test-messaging (rcv)', rcv_srt_process)
    except KeyboardInterrupt:
        logger.info('KeyboardInterrupt - Not implemented yet')
    except (
        ProcessHasNotBeenCreated,
        ProcessHasNotBeenStartedSuccessfully,
        # ProcessHasNotBeenTerminated,
        ProcessHasNotBeenKilled,
    ) as error:
        logger.info(
            f'Exception occured ({error.__class__.__name__}): {error}'
        )
    finally:
        logger.info('Terminating running processes')
        # TODO: Add go_further in a right way
        # go_further = True    
        if len(processes) == 0:
            logger.info('Nothing to terminate')
            return

        for name, process in reversed(processes):
            try:
                cleanup_process(name, process)
            except:
                # TODO: Collect the information regarding non killed processes
                # and perfom additional clean-up actions
                # Exceptions: ProcessIsNotKilled and others
                print('The next experiment can not be done further')
                # go_further = False
        # return go_further


if __name__ == '__main__':
    main()