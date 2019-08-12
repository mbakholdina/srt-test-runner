import enum
import logging
import pathlib
import time
import typing

import click

import perform_test, shared


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)-15s [%(levelname)s] %(message)s',
)
logger = logging.getLogger(__name__)


@enum.unique
class CombinedTestName(shared.AutoName):
    bw_filecc_loop_test = enum.auto()
    iterative_bw_loop_test = enum.auto()
    iterative_filecc_loop_test = enum.auto()

COMBINED_TEST_NAMES = [name for name, member in CombinedTestName.__members__.items()]


def bw_filecc_loop_test(
    config_filepath: str,
    snd_quantity: int,
    snd_mode: str,
    collect_stats: bool,
    run_tshark: bool,
    results_dir: str
):
    """ 
    Combined test which first runs Bandwidth Loop Test, and then after 10 seconds 
    waiting runs File CC Loop Test. Valid settings for both of tests 
    should be specified within config file in appropriate tests sections.

    NOTE: There is an option to determine maximum available bandwidth
    at the moment of running experiment and then streaming a file
    specifying this particular available bandwidth. This requires
    rewriting of config file on the fly using temporary files.
    Currently, all settings both for bandwidth loop test and file loop test
    should be specified within config file.
    """
    interval = 10
    rcv_mode = 'remotely'

    try:
        logger.info('Starting bandwidth loop test')
        perform_test.main_function(
            perform_test.TestName.bw_loop_test.value,
            config_filepath,
            rcv_mode,
            snd_quantity,
            snd_mode,
            collect_stats,
            run_tshark,
            results_dir + '/bw_loop_test'
        )
    except Exception as error:
        logger.info(
            f'During bandwidth loop test an exception occured ({error.__class__.__name__}): {error}. '
            f'File CC loop test can not be done.'
        )
        return

    logger.info(f'Waiting for {interval} s ...')
    time.sleep(interval)

    logger.info('Starting file cc loop test')
    perform_test.main_function(
        perform_test.TestName.filecc_loop_test.value,
        config_filepath,
        rcv_mode,
        snd_quantity,
        snd_mode,
        collect_stats,
        run_tshark,
        results_dir + '/filecc_loop_test'
    )

    logger.info('Done')


def iterative_test(
    combined_test_name,
    config_filepath: str,
    app: str,
    snd_quantity: int,
    snd_mode: str,
    collect_stats: bool,
    run_tshark: bool,
    iterations: int,
    interval: int,
    results_dir: str
):
    """ 
    Function which performs either iterative bandwidth loop test, or
    iterative file CC loop test.
    """
    logger.info(
            f'Starting {combined_test_name}. Iterations: {iterations}, '
            f'interval between iterations: {interval} s.'
    )

    if combined_test_name == CombinedTestName.iterative_bw_loop_test.value:
        test_name = perform_test.TestName.bw_loop_test.value
    if combined_test_name == CombinedTestName.iterative_filecc_loop_test.value:
        test_name = perform_test.TestName.filecc_loop_test.value

    for i in range(0, iterations):
        logger.info(f'Iteration: {i}')

        try:
            perform_test.main_function(
                test_name,
                config_filepath,
                app,
                'remotely',
                snd_quantity,
                snd_mode,
                collect_stats,
                run_tshark,
                results_dir + f'/iteration_{i}'
            )
        except Exception as error:
            logger.info(
                f'Exception occured ({error.__class__.__name__}): {error}. '
                f'Next iteration can not be done.'
            )
            break

        if i != (iterations - 1): 
            logger.info(f'Waiting for {interval} s ...')
            time.sleep(interval)

    logger.info('Done')


@click.command()
@click.argument(
    'combined_test_name',
    type=click.Choice(COMBINED_TEST_NAMES)
)
@click.argument(
    'config_filepath', 
    type=click.Path(exists=True)
)
@click.option(
    '--app',
    type=click.Choice(['srt-test-messaging', 'srt-xtransmit']),
    default='srt-test-messaging',
    help='SRT application to run.',
    show_default=True
)
@click.option(
    '--snd-quantity', 
    default=1,
    help=   'Number of senders to start.',
    show_default=True
)
@click.option(
    '--snd-mode',
    type=click.Choice(['serial', 'parallel']), 
    default='parallel',
    help='Start senders concurrently or in parallel.',
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
    '--results-dir',
    default='_results',
    help='Directory to store results.',
    show_default=True
)
@click.option(
    '--iterations',
    default=3,
    help='Number of iterations. Applicable for iterative tests only.',
    show_default=True
)
@click.option(
    '--interval',
    default=30,
    help='Interval between iterations in seconds. Applicable for iterative tests only.',
    show_default=True
)
def main(
    combined_test_name: str,
    config_filepath: str,
    app: str,
    snd_quantity: int,
    snd_mode: str,
    collect_stats: bool,
    run_tshark: bool,
    iterations: int,
    interval: int,
    results_dir: str
):
    if combined_test_name == CombinedTestName.bw_filecc_loop_test.value:
        bw_filecc_loop_test(
            config_filepath,
            snd_quantity,
            snd_mode,
            collect_stats,
            run_tshark,
            results_dir
        )

    if combined_test_name == CombinedTestName.iterative_bw_loop_test.value or CombinedTestName.iterative_filecc_loop_test.value:
        iterative_test(
            combined_test_name,
            config_filepath,
            app,
            snd_quantity,
            snd_mode,
            collect_stats,
            run_tshark,
            iterations,
            interval,
            results_dir
        )


if __name__ == '__main__':
    main()