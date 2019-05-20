""" 
A script that runs bandwidth loop test iteratively for a specified
number of times. 

iterations - number of times to run bandwidth loop test
time_to_sleep - time to sleep in between (in sec)
"""
import logging
import time


import test_messaging_bw_loop


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)-15s [%(levelname)s] %(message)s',
)
logger = logging.getLogger(__name__)


if __name__ == '__main__':
    iterations = 3
    time_to_sleep = 10

    for i in range(0, iterations):
        logger.info(f'Iteration: {i}')

        try:
            test_messaging_bw_loop.main_function(
                'scripts/python/config.ini',
                'remotely',
                2,
                'concurrently',
                f'_results_{i}',
                True,
                False
            )
        except Exception as error:
            logger.info(
                f'Exception occured ({error.__class__.__name__}): {error}. '
                f'Next iteration can not be done.'
            )
            break

        time.sleep(time_to_sleep)