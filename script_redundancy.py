# Script for testing redandancy feature
# The original code ia taken from here 
# https://github.com/Haivision/srt/pull/663
# https://github.com/maxlovic/srt/blob/tests/apps-autotest/scripts/python/test-apps.py
import logging
import time

import click

from new_processes import Process


logger = logging.getLogger(__name__)


def generate_buffer():
    return bytearray([(1 + i % 255) for i in range(0, 1315)]) + bytearray([0])


def calculate_interval(bitrate):
    if bitrate is None:
        return 0.01
    else:
        return (1316 * 8) / (bitrate * 1000000)


def start_sender(path, ip, port, interval, n):
    logger.info('Starting sender')
    args = [
        f'{path}',
        'file://con',
        f'srt://{ip}:{port}?nakreport=0&linger=0',
        # '-v', 
        # '-loglevel:error'
    ]
    process = Process('sender', args)
    process.start()

    # Sleep for 1s in order to give some time for sender and receiver 
    # to establish the connection
    time.sleep(1)

    buffer = generate_buffer()

    try:
        for i in range(0, n):
            if i < 2 or i > 5:
                logger.debug(f'Sending packet {i + 1}')
                time.sleep(interval)
                buffer[0] = 1 + i % 255
                process.process.stdin.write(buffer)
                process.process.stdin.flush()
    except KeyboardInterrupt:
        logger.info('KeyboardInterrupt has been caught')
    finally:
        # Sleep for 1s in order to give some time for sender to deliver 
        # the remain portion of packets at the end of experiment
        time.sleep(1)
        logger.info('Stopping sender')
        # TODO: Do not forget about fixing the bug in srt-live-transmit
        process.stop()


def start_receiver(path, port, n):
    logger.info('Starting receiver')
    args = [
        f'{path}',
        f'srt://:{port}?nakreport=0&linger=0',
        'file://con',
        # '-v', 
        # '-loglevel:error'
    ]
    process = Process('receiver', args)
    process.start()

    logger.info('!!! PLEASE START THE SENDER !!!')

    i = 0
    packets_lost = 0
    buffer = generate_buffer()
    target_values = buffer.copy()

    try:
        while i < n:
            target_values[0] = 1 + i % 255

            logger.debug('Waiting for data')
            data = process.process.stdout.read(1316)

            message = f'Packet {i + 1}, size {len(data)} '
            if target_values == data:
                logger.info(message + 'is valid')
            else:
                logger.error(message + 'is invalid')
                logger.info(f'Received: {data}')
                logger.info(f'Expected: {target_values}')
                dif = data[0] - target_values[0]
                packets_lost += + dif
                i += dif
            i += 1
    except KeyboardInterrupt:
        logger.info('KeyboardInterrupt has been caught')
    finally:
        logger.info('Stopping receiver')
        process.stop()
        
        if i != 0:
            logger.info(f'Packets expected: {n}')
            logger.info(f'Packets received: {i - packets_lost}')
            logger.info(f'Packets sent: {i}')
            logger.info(f'Packets not sent: {n - i}')
            logger.info(f'Packets lost: {packets_lost}')
            # packets_lost * 100 / packets_sent
            logger.info(f'Packets lost, %: {round(packets_lost * 100 / i, 2)}')


@click.group()
@click.option('--debug/--no-debug', default=False)
def cli(debug):
    if debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)-15s [%(levelname)s] %(message)s',
        )
    else:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)-15s [%(levelname)s] %(message)s',
        )


@cli.command()
@click.option('--ip', default='127.0.0.1', help='IP to call', show_default=True)
@click.option('--port', default=4200, help='Port to call', show_default=True)
@click.option('--duration', default=60, help='Duration, s', show_default=True)
@click.option('--n', help='Number of packets', type=int)
@click.option('--bitrate', help='Bitrate, Mbit/s', type=float)
@click.argument('path')
def sender(ip, port, duration, n, bitrate, path):
    interval = calculate_interval(bitrate)
    if n is None:
        n = int(duration // interval) + 1

    start_sender(path, ip, port, interval, n)


@cli.command()
@click.option('--port', default=4200, help='Port to listen', show_default=True)
@click.option('--duration', default=60, help='Duration, s', show_default=True)
@click.option('--n', help='Number of packets', type=int)
@click.option('--bitrate', help='Bitrate, Mbit/s', type=float)
@click.argument('path')
def receiver(port, duration, n, bitrate, path):
    interval = calculate_interval(bitrate)
    if n is None:
        n = int(duration // interval) + 1

    start_receiver(path, port, n)


if __name__ == '__main__':
    cli()