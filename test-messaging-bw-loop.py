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
            "{}, returncode {}".format(name, returncode)
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
    args = ['tshark', '-i', interface, '-f', 'udp port {}'.format(port), '-s', '1500', '-w', output]
    return create_process("tshark", args)


@click.command()
@click.argument('dst_ip',   default="192.168.0.110")
@click.argument('dst_port', default="4200")
@click.argument('algdesc')
@click.argument('prefix')
@click.option('--iface')
@click.option('--collect-pcapng', is_flag=True)
@click.option('--collect-stats', is_flag=True)
#@click.option('--startmbps', is_flag=True, help='Collect SRT statistics')
#@click.option('--stopmbps', is_flag=True, help='Collect SRT statistics')
def main(dst_ip, dst_port, algdesc, prefix, iface, collect_pcapng, collect_stats):
    common_args = ["./srt-test-messaging", "srt://{}:{}?rcvbuf=1000000000&sndbuf=1000000000&fc=800000&smoother=live".format(dst_ip, dst_port), "",
            "-msgsize", "1456", "-reply", "0", "-printmsg", "0"]

    if collect_stats:
        common_args += ['-statsfreq', '1']

    pc_name = 'srt-test-messaging (SND)'

    #mbps_to_check = [1, 5, 10] + [x for x in range(50, 1100, 50)]
    bps_to_check = [x for x in range(600, 2000, 50)]
    duration_sec = 30

    for mbps in bps_to_check:
        # Calculate number of packets for duration_sec sec of streaming
        # based on the target bitrate and packet size.
        bps = mbps * 1_000_000
        repeat = duration_sec * bps // (1456 * 8)
        maxbw  = int(bps // 8 * 1.25)

        if collect_pcapng:
            pcapng_file = prefix + "-alg-{}-blt-{}Mbps-snd.pcapng".format(algdesc, mbps)
            tshark = create_tshark(interface = iface, port = dst_port, output = pcapng_file)
            time.sleep(3)

        args = common_args + ["-bitrate", str(bps), "-repeat", str(repeat)]
        args[1] += "&maxbw={}".format(maxbw)

        if collect_stats:
            stats_file = prefix + "-alg-{}-blt-{}Mbps-snd-stats.csv".format(algdesc, mbps)
            args += ['-statsfile', stats_file]

        logger.info("Starting with bitrate {} Mbps, repeat {}".format(mbps, repeat))
        snd_srt_process = create_process(pc_name, args)

        sleep_sec = duration_sec
        is_running = True
        i = 0
        while is_running:
            is_running, returncode = process_is_running(snd_srt_process)
            if is_running:
                time.sleep(sleep_sec)
                sleep_sec = 1  # Next time sleep for 1 second to react on the process finished.
                i += 1

        logger.info("Done")
        if collect_pcapng:
            logger.info("Stopping tshark")
            time.sleep(3)
            cleanup_process("tshark", tshark)

        if i >= 5:
            logger.info("Waited {} seconds. {} Mbps is considered as maximum bandwidth".format(duration_sec + i, mbps))
            break

    # TODO: Start transmission in file mode with known bandwidth



if __name__ == '__main__':
    main()




