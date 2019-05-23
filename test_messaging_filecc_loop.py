import configparser
import logging
import pathlib
import signal
import shutil
import subprocess
import sys
import time

import attr
import click

import shared


# TODO:     Improve parsing config part for all the scripts,
#           Make one main function for both bandwidth loop test and filecc test
#           by means of adding a generator for returning SRT params and 
#           configuration, callbacks, and improving start sender/receiver with
#           any kind of params and options,


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)-15s [%(levelname)s] %(message)s',
)
logger = logging.getLogger(__name__)


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
            parsed_config['filecc-loop-test']['dst_host'],
            parsed_config['filecc-loop-test']['dst_port'],
            parsed_config['filecc-loop-test']['algdescr'],
            parsed_config['filecc-loop-test']['scenario'],
            int(parsed_config['filecc-loop-test']['time_to_stream'])
        )


# Packet size (B, Bytes)
PACKET_SIZE = 1472

def calculate_flow_control(snd_rate, rtt):
    """ 
    Attributes:
        snd_rate: 
            Sending rate (bps).
        rtt:
            Round trip time (ms).

    Returns:
        Flow control in packets.
    """
    fc = snd_rate * ((rtt + 10) / 1000) / 8 / PACKET_SIZE
    return int(round(fc, 0))

def calculate_buffer_size(fc):
    return 2 * fc * PACKET_SIZE

def get_query(snd_rate, rtt, smoother):
    # rcvbuf=1000000000&sndbuf=1000000000&fc=800000
    fc = calculate_flow_control(snd_rate, rtt)
    buffer_size = calculate_buffer_size(fc)
    query = f'rcvbuf={buffer_size}&sndbuf={buffer_size}&fc={fc}&smoother={smoother}'
    return query

def get_srt_receiver_command(
    config_filepath,
    msg_size: int,
    available_bandwidth: int,
    rtt: int,
    smoother,
    collect_stats: bool=False,
    results_dir=None
):
    config = Config.from_config_filepath(pathlib.Path(config_filepath))
    query = get_query(available_bandwidth, rtt, smoother)

    args = []
    # args += shared.SSH_COMMON_ARGS
    args += [
        # f'{rcv_ssh_username}@{rcv_ssh_host}',
        f'{config.rcv_path_to_srt}/srt-test-messaging',
        f'"srt://:{config.dst_port}?{query}"',
        '-msgsize', str(msg_size),
        '-reply', '0', 
        '-printmsg', '0'
    ]
    if collect_stats:
        filename = f'{config.scenario}-alg-{config.algdescr}-filecc-stats-rcv.csv'
        filepath = results_dir / filename
        args += [
            '-statsfreq', '1',
            '-statsfile', filepath,
        ]
    
    return f'{" ".join(args)}'

def start_sender(
    snd_path_to_srt,
    dst_host,
    dst_port,
    time_to_stream,
    msg_size,
    available_bandwidth,
    rtt,
    smoother,
    collect_stats: bool=False,
    results_dir=None,
    filename=None,
    sender_number=0
):
    name = f'srt sender {sender_number}'
    logger.info(f'Starting on a local machine: {name}')
    
    repeat = time_to_stream * available_bandwidth // (msg_size * 8)
    # We set the value of sending rate equal to available bandwidth,
    # because we would like to stream with the maximum available rate 
    query = get_query(available_bandwidth, rtt, smoother)
       
    args = []
    args += [
        f'{snd_path_to_srt}/srt-test-messaging', 
        f'srt://{dst_host}:{dst_port}?{query}',
        "",
        '-msgsize', str(msg_size),
        '-reply', '0', 
        '-printmsg', '0',
        '-repeat', str(repeat),
    ]
    if collect_stats:
        filepath = results_dir / filename
        args += [
            '-statsfreq', '1',
            '-statsfile', filepath,
        ]
    print(args)
    snd_srt_process = shared.create_process(name, args)
    logger.info(f'Started successfully: {name}')
    return (name, snd_srt_process)

def determine_msg_size(msg_size):
    if msg_size == '1456B':
        return 1456
    if msg_size == '4MB':
        return 4 * 1024 * 1024
    if msg_size == '8MB':
        return 8 * 1024 * 1024

def main_function(
    config_filepath,
    msg_size,
    bandwidth,
    rtt,
    smoother,
    # rcv,
    # snd_number,
    # snd_mode,
    # iterations,
    results_dir,
    collect_stats,
    run_tshark
):
    config = Config.from_config_filepath(pathlib.Path(config_filepath))

    logger.info('Creating a folder for saving results on a sender side')
    results_dir = pathlib.Path(results_dir)
    if results_dir.exists():
        shutil.rmtree(results_dir)
    results_dir.mkdir()
    logger.info('Created successfully')

    processes = []
    # for i in range(0, iterations):
        # logger.info(f'Iteration: {i}')

    # Start tshark on a sender side
    if run_tshark:
        filename = f'{config.scenario}-alg-{config.algdescr}-filecc-stats-snd.pcapng'
        snd_tshark_process = shared.start_tshark(
            config.snd_tshark_iface, 
            config.dst_port, 
            filename,
            results_dir
        )
        processes.append(snd_tshark_process)
        time.sleep(3)

    # Start srt sender on a sender side
    sender_processes = []
    filename = f'{config.scenario}-alg-{config.algdescr}-filecc-stats-snd.csv'
    snd_srt_process = start_sender(
        config.snd_path_to_srt,
        config.dst_host,
        config.dst_port,
        config.time_to_stream,
        msg_size,
        bandwidth,
        rtt,
        smoother,
        collect_stats,
        results_dir,
        filename
    )
    processes.append(snd_srt_process)
    sender_processes.append(snd_srt_process)

    # Sleep for config.time_to_stream seconds to wait while senders 
    # will finish the streaming and then check how many senders are 
    # still running.
    time.sleep(config.time_to_stream)
    extra_time = shared.calculate_extra_time(sender_processes)
    logger.info(f'Extra time spent on streaming: {extra_time}')

    logger.info('Done')
    time.sleep(3)

    if run_tshark:
        shared.cleanup_process(snd_tshark_process)
        time.sleep(3)

@click.command()
@click.argument(
    'config_filepath', 
    type=click.Path(exists=True)
)
# @click.option(
#     '--rcv', 
#     type=click.Choice(['manually', 'remotely']), 
#     default='remotely',
#     help=	'Start a receiver manually or remotely via SSH. In case of '
#             'manual receiver start, please do not forget to do it '
#             'before running the script.',
#     show_default=True
# )
# @click.option(
#     '--snd-number', 
#     default=1,
#     help=   'Number of senders to start.',
#     show_default=True
# )
# @click.option(
#     '--snd-mode',
#     type=click.Choice(['concurrently', 'parallel']), 
#     default='concurrently',
#     help=   'Start senders concurrently or in parallel.',
#     show_default=True
# )
@click.option(
    '--msg_size',
    type=click.Choice(['1456B', '4MB', '8MB']), 
    default='1456B',
    help=   'Message size.',
    show_default=True
)
@click.option(
    '--bandwidth',
    default='1000000000',
    help=   'Available bandwidth (bytes).',
    show_default=True
)
@click.option(
    '--rtt',
    default='20',
    help=   'RTT (ms).',
    show_default=True
)
@click.option(
    '--smoother',
    type=click.Choice(['file', 'file-v2']), 
    default='file-v2',
    help=   'Smoother type.',
    show_default=True
)
# @click.option(
#     '--iterations',
#     default='1',
#     help=   'Number of iterations.',
#     show_default=True
# )
@click.option(
    '--results-dir',
    default='_results',
    help=   'Directory to store results.',
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
@click.option(
    '--rcv-cmd',
    is_flag=True,
    help='Get command to start receiver.'
)

def main(
    config_filepath,
    msg_size,
    bandwidth,
    rtt,
    smoother,
    # rcv,
    # snd_number,
    # snd_mode,
    # iterations,
    results_dir,
    collect_stats,
    run_tshark,
    rcv_cmd
):
    msg_size = determine_msg_size(msg_size)
    available_bandwidth = int(bandwidth)
    rtt = int(rtt)
    # iterations = int(iterations)

    if rcv_cmd:
        cmd = get_srt_receiver_command(
            config_filepath,
            msg_size,
            available_bandwidth,
            rtt,
            smoother,
            collect_stats,
            results_dir
        )
        # ! stop here
        print(cmd)
        return

    main_function(
        config_filepath,
        msg_size,
        available_bandwidth,
        rtt,
        smoother,
        # rcv,
        # snd_number,
        # snd_mode,
        # iterations,
        results_dir,
        collect_stats,
        run_tshark
    )


if __name__ == '__main__':
    main()