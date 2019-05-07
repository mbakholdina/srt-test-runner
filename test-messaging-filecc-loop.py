import sys
import time
import subprocess
import signal
import logging
import click
from threading import Thread




logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)-15s [%(levelname)s] %(message)s',
)
logger = logging.getLogger(__name__)


class ProcessHasNotBeenCreated(Exception):
    pass

class ProcessHasNotBeenStartedSuccessfully(Exception):
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



def create_process(name, args):
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
                #stderr=subprocess.PIPE,
                universal_newlines=False,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                bufsize=1
            )
        else:
            process = subprocess.Popen(
                args, 
                #stdin =subprocess.PIPE,
                #stdout=subprocess.PIPE,
                #stderr=subprocess.PIPE,
                #universal_newlines=False,
                bufsize=1
            )
    except OSError as e:
        raise ProcessHasNotBeenCreated('{}. Error: {}'.format(name, e))

    # Check that the process has started successfully and has not terminated
    # because of an error
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

    # FIXME: Signals may not work on Windows properly. Might be useful
    # https://stefan.sofa-rockers.org/2013/08/15/handling-sub-process-hierarchies-python-linux-os-x/
    #process.stdout.close()
    #process.stdin.close()
    logger.debug('Terminating the process: {}'.format(name))
    logger.debug('OS: {}'.format(sys.platform))

    sig = signal.CTRL_C_EVENT if sys.platform == 'win32' else signal.SIGINT
    #if sys.platform == 'win32':
    #    if sig in [signal.SIGINT, signal.CTRL_C_EVENT]:
    #        sig = signal.CTRL_C_EVENT
    #    elif sig in [signal.SIGBREAK, signal.CTRL_BREAK_EVENT]:
    #        sig = signal.CTRL_BREAK_EVENT
    #    else:
    #        sig = signal.SIGTERM

    process.send_signal(sig)
    for i in range(3):
        time.sleep(1)
        is_running, returncode = process_is_running(process)
        if not is_running: 
            logger.debug('Terminated')
            return

    # TODO: (For future) Experiment with this more. If stransmit will not 
    # stop after several terminations, there is a problem, and kill() will
    # hide this problem in this case.
    
    # TODO: (!) There is a problem with tsp, it's actually not killed
    # however process_is_running(process) becomes False
    is_running, _ = process_is_running(process)
    if is_running:
        logger.debug('Killing the process: {}'.format(name))
        process.kill()
        time.sleep(1)
    is_running, _ = process_is_running(process)
    if is_running:
        raise ProcessHasNotBeenKilled('{}, id: {}'.format(name, process.pid))
    logger.debug('Killed')



def create_tshark(interface, port, output):
    args = ['tshark', '-i', interface, '-f', '"udp port {}"'.format(port), '-s', '1500', '-w', output]
    return create_process("tshark", args)



@click.command()
@click.argument('dst_ip',   default="192.168.0.110")
@click.argument('dst_port', default="4200")
@click.argument('algdesc')
@click.argument('pcapng')
@click.argument('iface')
@click.option('--collect-stats', is_flag=True, help='Collect SRT statistics')
def main(dst_ip, dst_port, algdesc, pcapng, iface, collect_stats):
    #common_args = ["./srt-test-messaging", "srt://{}:{}?sndbuf=12058624&smoother=live".format(dst_ip, dst_port), "",
    #        "-msgsize", "1456", "-reply", "0", "-printmsg", "0"]
    common_args = ["./srt-test-messaging", "srt://{}:{}".format(dst_ip, dst_port), "",
            "-reply", "0", "-printmsg", "0"]
    if collect_stats:
        common_args += ['-statsfreq', '1']

    pc_name = 'srt-test-messaging (SND)'
    target_time_s = 120
    expected_bitrate_bps = 500000000 # 500 Mbps
    message_size = 8 * 1024 * 1024

    for i in range(0, 2):
        # Calculate number of packets for 20 sec of streaming
        # based on the target bitrate and packet size.
        repeat = target_time_s * expected_bitrate_bps // (message_size * 8)
        maxbw  = int(expected_bitrate_bps // 8 * 1.25)
        args = common_args + ["-repeat", str(repeat)]
        if collect_stats:
            stats_file = pcapng + "-alg-{}-take-{}.csv".format(algdesc, i)
            args += ['-statsfile', stats_file]
        logger.info("Starting with bitrate {}, repeat {}".format(expected_bitrate_bps, repeat))

        pcapng_file = pcapng + "-alg-{}-take-{}.pcapng".format(algdesc, i)
        tshark = create_tshark(interface = iface, port = dst_port, output = pcapng_file)
        time.sleep(3)

        snd_srt_process = create_process(pc_name, args)

        sleep_s = 20
        is_running = True
        while is_running:
            is_running, returncode = process_is_running(snd_srt_process)
            if is_running:
                time.sleep(sleep_s)
                sleep_s = 1  # Next time sleep for 1 second to react on the process finished.

        logger.info("Done")
        time.sleep(3)
        cleanup_process("tshark", tshark)




if __name__ == '__main__':
    main()




