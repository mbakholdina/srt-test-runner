import logging
import pathlib
import signal
import subprocess
import sys
import time
import typing

from new_enums import ProcessStatus


logger = logging.getLogger(__name__)


# ? Do I need this
SSH_CONNECTION_TIMEOUT = 10


class ProcessNotStarted(Exception):
    pass

class ProcessNotTerminated(Exception):
    pass

class ProcessNotKilled(Exception):
    pass

class ProcessNotStopped(Exception):
    pass


class Process:
    def __init__(self, name, args, via_ssh: bool=False):
        self.name = name
        self.args = args
        # TODO: change via_ssh to timeouts (for start, for stop - depending on object and 
        # whether it is starte via ssh or locally)
        self.via_ssh = via_ssh

        self.process = None
        self.is_started = False

    def start(self):
        """ 
        Raises:
            ValueError
            ProcessNotStarted
        """
        logger.debug(f'Starting a process: {self.name}')
        if self.is_started:
            raise ValueError(
                f'Process has been started already: {self.name}, '
                f'{self.process}. Start can not be done'
            )

        try:
            if sys.platform == 'win32':
                self.process = subprocess.Popen(
                    self.args, 
                    stdin =subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=False,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                    bufsize=1
                )
            else:
                self.process = subprocess.Popen(
                    self.args, 
                    stdin =subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    #universal_newlines=False,
                    bufsize=1
                )
            self.is_started = True
        except OSError as e:
            raise ProcessNotStarted(f'{self.name}. Error: {e}')
    
        # TODO: Adjust timers
        # Check that the process has started successfully and has not terminated
        # because of an error
        if self.via_ssh:
            time.sleep(SSH_CONNECTION_TIMEOUT + 1)
        else:
            # FIXME: Find a better solution, I changed the time from 1 to 5 s,
            # cause it was not enough in case of errors with srt-test-messaging
            # app, e.g. when starting the caller first and there is no listener yet
            # NOTE: A good thing to consider - what would be in case the child process
            # finfishes its work earlier than the time specified (5s). It is
            # important to consider especially in case of fsrt and small files
            # transmission.
            time.sleep(5)

        is_running, returncode = self.get_status()
        if not is_running:
            raise ProcessNotStarted(
                f'{self.name}, returncode: {returncode}, '
                f'stdout: {self.process.stdout.readlines()}, '
                f'stderr: {self.process.stderr.readlines()}'
            )
    
        logger.debug(f'Started: {self.name}, {self.process}')


    def _terminate(self):
        logger.debug(f'Terminating the process: {self.name}, {self.process}')

        if not self.is_started:
            raise ValueError(
                f'Process has not been started yet: {self.name}. '
                'Terminate can not be done'
            )

        status, _ = self.get_status()
        if status == ProcessStatus.idle: 
            logger.debug(f'Process is idle, no need to terminate')
            return
        
        sig = signal.CTRL_C_EVENT if sys.platform == 'win32' else signal.SIGINT
        self.process.send_signal(sig)
        for i in range(3):
            time.sleep(1)
            status, _ = self.get_status()
            if status == ProcessStatus.idle: 
                logger.debug(f'Terminated: {self.name}, {self.process}')
                return

        raise ProcessNotTerminated(f'{self.name}, {self.process}')


    def _kill(self):
        logger.debug(f'Killing the process: {self.name}, {self.process}')

        if not self.is_started:
            raise ValueError(
                f'Process has not been started yet: {self.name}. '
                'Kill can not be done'
            )

        status, _ = self.get_status()
        if status == ProcessStatus.idle: 
            logger.debug(f'Process is idle, no need to kill')
            return

        self.process.kill()
        time.sleep(1)

        status, _ = self.get_status()
        if status == ProcessStatus.running:
            # ? Do I need an ID here
            raise ProcessNotKilled(f'{self.name}, id: {self.process.pid}')
            
        logger.debug(f'Killed: {self.name}, {self.process}')


    def stop(self):
        """ 
        Raises:
            ValueError
            ProcessNotStopped
        """
        logger.debug(f'Stopping the process: {self.name}, {self.process}')

        if not self.is_started:
            raise ValueError(
                f'Process has not been started yet: {self.name}. '
                f'Stop can not be done'
            )

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

        try:
            self._terminate()
        except ProcessNotTerminated:
            logger.error('Failed to terminate the process', exc_info=True)

            # TODO: (For future) Experiment with this more. If stransmit will not 
            # stop after several terminations, there is a problem, and kill() will
            # hide this problem in this case.
            
            # TODO: (!) There is a problem with tsp, it's actually not killed
            # however process_is_running(process) becomes False

            try:
                self._kill()
            except ProcessNotKilled as e:
                logger.error('Failed to kill the process', exc_info=True)
                raise ProcessNotStopped(f'{self.name}, {self.process}')
  
        # ? Test this
        # self.is_started = False

        logger.debug(f'Stopped: {self.name}, {self.process}')


    def get_status(self):
        """ 
        Returns:
            A tuple of (result, returncode) where 
            - is_running is equal to True if the process is running and False if
            the process has terminated,
            - returncode is None if the process is running and the actual value 
            of returncode if the process has terminated.
        """
        if not self.is_started:
            raise ValueError(
                f'Process has not been started yet: {self.name}.'
                f"Can't get the status"
            )

        returncode = self.process.poll()
        status = ProcessStatus.running if returncode is None else ProcessStatus.idle
        return (status, returncode)