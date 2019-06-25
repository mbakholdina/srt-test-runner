import logging
import pathlib
import time
import typing

import click

import perform_test


# TODO:     Implement iterative bandwidth loop test if needed


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)-15s [%(levelname)s] %(message)s',
)
logger = logging.getLogger(__name__)


def iterative_bw_loop_test():
    # TODO: Implement
    # iterations = 3
    # time_to_sleep = 10

    # for i in range(0, iterations):
    #     logger.info(f'Iteration: {i}')

    #     try:
    #         test_messaging_bw_loop.main_function(
    #             'scripts/python/config.ini',
    #             'remotely',
    #             2,
    #             'concurrently',
    #             f'_results_{i}',
    #             True,
    #             False
    #         )
    #     except Exception as error:
    #         logger.info(
    #             f'Exception occured ({error.__class__.__name__}): {error}. '
    #             f'Next iteration can not be done.'
    #         )
    #         break

    #     time.sleep(time_to_sleep)
    pass

@click.command()
@click.argument(
    'config_filepath', 
    type=click.Path(exists=True)
)
@click.option(
    '--rcv', 
    type=click.Choice(['manually', 'remotely']), 
    default='remotely',
    help=	'Start a receiver manually or remotely via SSH. In case of '
            'manual receiver start, please do not forget to do it '
            'before running the script.',
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
    help=   'Start senders concurrently or in parallel.',
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
    help=   'Directory to store results.',
    show_default=True
)
def main(
    config_filepath: str,
    rcv: str,
    snd_quantity: int,
    snd_mode: str,
    collect_stats: bool,
    run_tshark: bool,
    results_dir: typing.Optional[pathlib.Path]=None
):
    # NOTE: There is an option to determine maximum available bandwidth
    # at the moment of running experiment and then streaming a file
    # specifying this particular available bandwidth. This requires
    # rewriting of config file on the fly using temporary files.
    # Currently, all settings both for bandwidth loop test and file loop test
    # should be specified within config file.
    try:
        logger.info('Starting bandwidth loop test')
        perform_test.main_function(
            perform_test.TestName.bw_loop_test.value,
            config_filepath,
            rcv,
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

    time.sleep(10)
    logger.info('Starting file cc loop test')
    perform_test.main_function(
        perform_test.TestName.filecc_loop_test.value,
        config_filepath,
        rcv,
        snd_quantity,
        snd_mode,
        collect_stats,
        run_tshark,
        results_dir + '/filecc_loop_test'
    )


if __name__ == '__main__':
    main()