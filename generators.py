import configparser
import pathlib
import typing

import attr

import shared

# TODO:     Make constructors from section instead of filepath,
#           Check whether generator will work as a property of ExperimentParams


@attr.s
class GlobalConfig:
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

    
    @classmethod
    def from_config_filepath(cls, config_filepath: pathlib.Path):
        parsed_config = configparser.ConfigParser()
        with config_filepath.open('r', encoding='utf-8') as fp:
            parsed_config.read_file(fp)
        return cls(
            parsed_config['global']['rcv_ssh_host'],
            parsed_config['global']['rcv_ssh_username'],
            parsed_config['global']['rcv_path_to_srt'],
            parsed_config['global']['snd_path_to_srt'],
            parsed_config['global']['snd_tshark_iface'],
            parsed_config['global']['dst_host'],
            parsed_config['global']['dst_port'],
            parsed_config['global']['algdescr'],
            parsed_config['global']['scenario']
        )


@attr.s
class BandwidthLoopTestConfig:
    """
    Bandwidth loop test config.
    """
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
            int(parsed_config['bw-loop-test']['bitrate_min']),
            int(parsed_config['bw-loop-test']['bitrate_max']),
            int(parsed_config['bw-loop-test']['bitrate_step']),
            int(parsed_config['bw-loop-test']['time_to_stream'])
        )

def determine_msg_size(msg_size: str):
    """ In Bytes """
    if msg_size == '1456B':
        return 1456
    if msg_size == '4MB':
        return 4 * 1024 * 1024
    if msg_size == '8MB':
        return 8 * 1024 * 1024


@attr.s
class FileCCLoopTestConfig:
    """
    File CC (Congestion Control) loop test config.
    """ 
    msg_size: int = attr.ib()
    bandwidth: int = attr.ib()
    rtt: int = attr.ib()
    smoothers: typing.List[str] = attr.ib()
    time_to_stream: int = attr.ib()

    @classmethod
    def from_config_filepath(cls, config_filepath: pathlib.Path):
        parsed_config = configparser.ConfigParser()
        with config_filepath.open('r', encoding='utf-8') as fp:
            parsed_config.read_file(fp)

        return cls(
            determine_msg_size(parsed_config['filecc-loop-test']['msg_size']),
            int(parsed_config['filecc-loop-test']['bandwidth']),
            int(parsed_config['filecc-loop-test']['rtt']),
            parsed_config['filecc-loop-test']['smoother'].split(','),
            int(parsed_config['filecc-loop-test']['time_to_stream'])
        )


@attr.s
class ExperimentParams:
    # TODO: Make default = None
    rcv_attrs_values: typing.Optional[typing.List[typing.Tuple[str, str]]] = attr.ib()
    rcv_options_values: typing.Optional[typing.List[typing.Tuple[str, str]]] = attr.ib()
    snd_attrs_values: typing.Optional[typing.List[typing.Tuple[str, str]]] = attr.ib()
    snd_options_values: typing.Optional[typing.List[typing.Tuple[str, str]]] = attr.ib()
    # in bps
    bitrate: int = attr.ib()
    # Information needed to form .csv stats and .pcapng WireShark
    # files' names
    description: str = attr.ib()
    # in s
    time_to_stream: int = attr.ib()


def bw_loop_test_generator(
    global_config,
    test_config
):

    # TODO: Check whether it will work as a property of ExperimentParams

    for bitrate in range(test_config.bitrate_min, test_config.bitrate_max, test_config.bitrate_step):
        # Calculate number of packets for time_to_stream sec of streaming
        # based on the target bitrate and packet size
        repeat = test_config.time_to_stream * bitrate // (1456 * 8)
        maxbw  = int(bitrate // 8 * 1.25)
        
        rcv_attrs_values = [
            ('rcvbuf', '12058624'), 
            ('smoother', 'live'), 
            ('maxcon', '50')
        ]
        rcv_options_values = [
            ('-msgsize', '1456'), 
            ('-reply', '0'), 
            ('-printmsg', '0')
        ]
        snd_attrs_values = [
            ('sndbuf', '12058624'), 
            ('smoother', 'live'), 
            ('maxbw', str(maxbw)),
        ]
        snd_options_values = [
            ('-msgsize', '1456'), 
            ('-reply', '0'), 
            ('-printmsg', '0'), 
            ('-bitrate', str(bitrate)),
            ('-repeat', str(repeat)),
        ]
        description = f'{global_config.scenario}-alg-{global_config.algdescr}-bitr-{bitrate / shared.DELIMETER}Mbps'
        
        exper_params = ExperimentParams(
            rcv_attrs_values,
            rcv_options_values,
            snd_attrs_values,
            snd_options_values,
            bitrate,
            description,
            test_config.time_to_stream
        )

        yield exper_params


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
    # FIXME: Adjust formula
    # fc = snd_rate * ((rtt + 10) / 1000) * 2 / PACKET_SIZE
    # return int(round(fc, 0))
    return 60000

def calculate_buffer_size(msg_size, fc):
    # FIXME: Adjust formula
    # return max(2 * fc * PACKET_SIZE, 5 * msg_size)
    # 1Gb in bytes
    return 125000000


def filecc_loop_test_generator(
    global_config,
    test_config
):

    # TODO: Check whether it will work as a property of ExperimentParams

    for smoother in test_config.smoothers:
        # Calculate number of packets for time_to_stream sec of streaming
        # based on the available bandwidth (in bytes) and message size
        repeat = test_config.time_to_stream * test_config.bandwidth // test_config.msg_size
        # We set the value of sending rate equal to available bandwidth,
        # because we would like to stream with the maximum available rate 
        fc = calculate_flow_control(test_config.bandwidth, test_config.rtt)
        buffer_size = calculate_buffer_size(test_config.msg_size, fc)
        
        rcv_attrs_values = [
            ('rcvbuf', str(buffer_size)),
            ('sndbuf', str(buffer_size)),
            ('fc', str(fc)),
            ('smoother', smoother),
        ]
        rcv_options_values = [
            ('-msgsize', str(test_config.msg_size)), 
            ('-reply', '0'), 
            ('-printmsg', '0')
        ]
        snd_attrs_values = rcv_attrs_values
        snd_options_values = [
            ('-msgsize', str(test_config.msg_size)), 
            ('-reply', '0'), 
            ('-printmsg', '0'),
            ('-repeat', str(repeat)),
        ]
        description = f'{global_config.scenario}-alg-{global_config.algdescr}-msg_size-{test_config.msg_size}-smoother-{smoother}'
        
        exper_params = ExperimentParams(
            rcv_attrs_values,
            rcv_options_values,
            snd_attrs_values,
            snd_options_values,
            test_config.bandwidth * 8,
            description,
            test_config.time_to_stream
        )

        yield exper_params