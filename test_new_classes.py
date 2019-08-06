import pytest

import new_classes


TSHARK_CONFIG = {
    'interface': 'en0',
    'port': 4200,
    'dirpath': '_results',
    'filename': 'tshark_dump',
}

SRT_TEST_MESSAGING_CONFIG = {
    'path': '/Users/msharabayko/projects/srt/srt-maxlovic/_build',
    'type': 'rcv',
    'host': '',
    'port': '4200',
    'attrs_values': [
        ('rcvbuf', '12058624'),
        ('congestion', 'live'),
        ('maxcon', '50'),
    ],
    'options_values': [
        ('-msgsize', '1456'),
        ('-reply', '0'),
        ('-printmsg', '0'),
    ],
    'collect_stats': True,
    'description': 'busy_waiting',
    'dirpath': '_results',
} 

SUBPROCESS_CONFIG = None

SSH_SUBPROCESS_CONFIG = {
    'username': 'msharabayko',
    'host': '65.52.227.197',
}


OBJECTS_CLASSES = [
    ('tshark', TSHARK_CONFIG, new_classes.Tshark),
    ('srt-test-messaging', SRT_TEST_MESSAGING_CONFIG, new_classes.SrtTestMessaging),
]

@pytest.mark.parametrize('obj_type, obj_config, class_name', OBJECTS_CLASSES)
def test_factory_creates_right_object(obj_type, obj_config, class_name):
    factory = new_classes.SimpleFactory()
    obj = factory.create_object(obj_type, obj_config)
    assert isinstance(obj, class_name)


RUNNERS_CLASSES = [
    ('subprocess', SUBPROCESS_CONFIG, new_classes.Subprocess),
    ('ssh-subprocess', SSH_SUBPROCESS_CONFIG, new_classes.SSHSubprocess),
]

@pytest.mark.parametrize('runner_type, runner_config, class_name', RUNNERS_CLASSES)
def test_factory_creates_right_runner(runner_type, runner_config, class_name):
    factory = new_classes.SimpleFactory()
    obj = factory.create_object('tshark', TSHARK_CONFIG)
    runner = factory.create_runner(obj, runner_type, runner_config)
    assert isinstance(runner, class_name)


# TODO: Tests for IObject.make_args()
#       Fucntional tests: IRunner.start(), stop() with get_status() and ps -A