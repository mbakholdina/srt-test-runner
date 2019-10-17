# srt-test-runner

Scripts designed to evaluate the correctness and effectiveness of different algorithms implementation in SRT. [SRT](https://github.com/Haivision/srt) stands for Secure Reliable Transport and is an open source transport technology that optimizes streaming performance across unpredictable networks, such as the Internet.

Tests implemented:

* [Bandwidth Loop Test](#bandwidth-loop-test) to determine the maximum available bandwidth at the moment of running the script,
* [File CC Loop Test](#filecc-loop-test) to evaluate the different congestion control algorithms implemented in SRT,
* [Combined Bandwidth and File CC Loop Test](#bw-filecc-loop-test) to run both Bandwidth and File CC Loop tests one after another,
* [Iterative Bandwidth Loop Test](#iterative-bw-loop-test) which runs [Bandwidth Loop Test](#bandwidth-loop-test) iteratively at defined time periods,
* [Iterative File CC Loop Test](#iterative-filecc-loop-test) which runs [File CC Loop Test](#filecc-loop-test) iteratively at defined time periods.

# Terminology and Notes

## Terminology

One experiment is an operation or procedure carried out under controlled conditions in order to discover an unknown effect or law, to test or establish a hypothesis, or to illustrate a known law. For example, to us a set of the following steps 
* start SRT sender on one machine,
* start SRT receiver on another machine,
* wait for the specified time to have sender and receiver connected and SRT streaming finished,
* collect all the statistics (SRT stats, WireShark dumps),

is one experiment.

One test is a set of experiments executed in a consecutive order with different input parameters. The same example as above, however, the same steps are performed several times, e.g. to test SRT live streaming mode with different values of bitrate. In this case, bitrate value is that particular input parameter that is changed from experiment to experiment during the test.

One combined test is a procedure that consists of running several tests in order to execute: 1) the same test iteratively at defined intervals of time; 2) one test after another where the results of the first one can be input parameters for the second.

## Notes

CC - Congestion Control

# Getting Started

## Requirements

* python 3.6+
* tshark
* ssh-agent
* SRT test application `srt-test-messaging` built on both receiver and sender side

To install python libraries use:
```
pip install -r requirements.txt
```

## Setting up tshark

The following steps are valid for Ubuntu 18. For the other platforms, perform similar steps.

```
sudo apt-get install tshark
```

When asked whether to allow members of the wireshark group to capture packets on network
interfaces, answer `<Yes>`. This will allow to run `tshark` without elevated privileges. See section I./b. [Installing dumpcap and allowing non-root users to capture packets](https://wiki.wireshark.org/CaptureSetup/CapturePrivileges).


Finally add the user to wireshark group.
```
sudo usermod -a -G wireshark {username}
```

A logout is required for the changes to be applyed.

### CentOS 7

```
whereis tshark
sudo setcap cap_net_raw,cap_net_admin+eip /usr/local/bin/tshark
sudo setcap cap_net_raw,cap_net_admin+eip /usr/local/bin/dumpcap
sudo setcap cap_net_raw,cap_net_admin+eip /usr/sbin/tshark
sudo setcap cap_net_raw,cap_net_admin+eip /usr/sbin/dumpcap
```

## Setting up ssh-agent

In order to be able to run things remotely via SSH, there is a need to generate an SSH key on machine where the scripts will be run and copy this key to all remote machines.

Before running the script, an ssh-agent should be started in the backround and an appropriate SSH private key should be added in it
to store the passphrase in the keychain. Without doing this, scripts will raise an exception `paramiko.ssh_exception.SSHException`.

## Building `srt-test-messaging` test application

`srt-test-messaging` application is used for the tests. The latest version is located in `https://github.com/maxlovic/srt` repo, `feature/messaging_bidir_update2` branch.

In order to build it, make sure that dependensies needed for SRT project are installed (see [README](https://github.com/Haivision/srt/blob/master/README.md) for details), and then execute the following commands:
```
mkdir _build && cd _build
cmake ../ -DENABLE_MESSAGING_LIB=ON -DENABLE_TESTING=ON
cmake --build ./
```

# Tests Implemented

For the time being, there are two tests implemented:
* [Bandwidth Loop Test](#bandwidth-loop-test),
* [File CC Loop Test](#filecc-loop-test).

Both of them can be performed by means of running `perform_test.py` script. Test name should be passed as an argument to a script as well as config filepath. Usage
```
perform_test.py [OPTIONS] [bw_loop_test|filecc_loop_test] CONFIG_FILEPATH
```

Use `--help` option in order to get the full list of options 
```
  --rcv [manually|remotely]     Start a receiver manually or remotely via SSH.
                                In case of manual receiver start, please do
                                not forget to do it before running the script.
                                [default: remotely]
  --snd-quantity INTEGER        Number of senders to start.  [default: 1]
  --snd-mode [serial|parallel]  Start senders concurrently or in parallel.
                                [default: parallel]
  --collect-stats               Collect SRT statistics.
  --run-tshark                  Run tshark.
  --results-dir TEXT            Directory to store results.  [default:
                                _results]
  --help                        Show this message and exit.
```

Config file example
```
[global]
; Receiver
rcv_ssh_host = 137.135.161.223
rcv_ssh_username = msharabayko
; Path to srt-test-messaging application
rcv_path_to_srt = ~/projects/srt-maxlovic/_build
; Sender
; Path to srt-test-messaging application
;snd_path_to_srt = .
snd_path_to_srt = /Users/msharabayko/projects/srt/srt-maxlovic/_build
snd_tshark_iface = en0
; Destination host, port
dst_host = 137.135.161.223
dst_port = 4200
; Algorithm description (SRT build option)
algdescr = busy_waiting
; Test case scenario
scenario = eunorth_useast

; tests
[bw-loop-test]
; Bitrate boundaries and step for streaming (bps)
; If you would like to stream only with one value of bitrate,
; specify the value of bitrate_max <= bitrate_min + step
bitrate_min = 1000000
bitrate_max = 2000000
bitrate_step = 1000000
; Time to stream (s). Default value is 20s
time_to_stream = 30

[filecc-loop-test]
; Message size: 1456B, 4MB, 8MB
msg_size = 8MB
; Available bandwidth (bytes)
; bandwidth = 125000000
bandwidth = 125000
; RTT (ms)
rtt = 20
; Congestion control type: file, file-v2
; You can specify either one CC type or both of them using "," delimeter
; congestion = file
; congestion = file,file-v2
congestion = filev2
; Time to stream (s). Default value is 120s
time_to_stream = 120
```

Depending on which test is being performed, an appropriate section `bw-loop-test` or `filecc-loop-test` with input parameters is used. `global` section is obligitory. It describes test setup: IP addresses, SSH credentials, and other information.

## Experiment Description and Test Setup

For the time being, one experiment consists of the following steps:
1. Start tshark application on a receiver remotely if both `--rcv=remotely` and `--run-tshark` option is on.
2. Start receiver manually or remotely via SSH depending on the value of `--rcv` option. In case of manual receiver start, it should be done before running the script.
3. Start tshark application on a sender side depending on `--run-tshark` option.
4. Start one or several SRT senders (`--snd-quantity` option) on a sender side to stream for `time_to_stream` seconds specified in an appropriate test section of config file. Senders can be started both in parallel or serial mode depending on `--snd-mode` option. However, some time adjustments and additional testing is needed for serial mode. Currently, only parallel mode is used.
5. Sleep for `time_to_stream` seconds to wait while senders will finish the streaming and then check how many senders are still running.
6. Calculate extra time spent on streaming.

`srt-test-messaging` testing application is used in this experiment. As mentioned above, receiver application can be started either manually, or on a remote machine whithin the script. For now, sender application is started locally on a machine where the script is running. Remote machine support is planned to be implemented.

`tshark` application is runned in a separate process locally on a sender side to capture outcoming network traffic and remotely via SSH on a receiver side to capture incoming traffic.

At the same time depending on `--collect-stats` option, `srt-test-messaging` testing application writes SRT core statistics to a .csv file in a directory specified within `--results-dir` option. Filename is generated within the script depending on test name and input parameters.

## Tests Description

### <a name="bandwidth-loop-test"></a> 1. Bandwidth Loop Test

The purpose of Bandwidth Loop Test is to determine the maximum available bandwidth at the moment of running the script.

`srt-test-messaging` testing application is used to produce data with specified bitrates to send it over the network.
The script loops through several sending bitrates, starting with `bitrate_min`, ending with `bitrate_max`, with a specified step `bitrate_step` in bps. The amount of packets to be sent is calculated based on the specified bitrate and the specified duration of the experiment. The duration of each run is set to `time_to_stream` seconds. All the settings should be specified within `bw-loop-test` section of config file.

The script measures the time spent by the application to transmit the generated amount of data packets. If the time spent exceeds 5 seconds, the last used bitrate should be considerd to be an available bandwidth of the network link.

#### Combinations Tested

* snd-quantity = 1 or higher
* snd-mode = parallel

#### Configuration and Command Line Examples for srt-test-messaging  Test Application

##### Receiver

* rcvbuf (Receiving buffer): 12058624 (attribute)
* smoother (Congestion Control algorithm): live (attribute)
* maxcon: 50 (attribute)
* msg_size (Message size): 1456 (option)
* reply: 0 (option)
* printmsg: 0 (option)

An example of command line for `srt-test-messaging`, generated by the script:
```
./srt-test-messaging' "srt://:4200?rcvbuf=12058624&smoother=live&maxcon=50" -msgsize 1456 -reply 0 -printmsg 0 -statsfreq 1 -statsfile _results/eunorth_useast-alg-busy_waiting-bitr-1.0Mbps-stats-rcv.csv
```

##### Sender

* sndbuf (Sending buffer): 12058624 (attribute)
* smoother (Congestion Control algorithm): live (attribute)
* maxbw (Maximum bandwidth): calculated as int(bitrate // 8 * 1.25) (attribute)
* msg_size (Message size): 1456 (option)
* reply: 0 (option)
* printmsg: 0 (option)
* bitrate (Current value of bitrate): bitrate
* repeat (Number of messages to send): calculated as time_to_stream * bitrate // (1456 * 8) (option)

An example of command line for `srt-test-messaging`, generated by the script:
```
./srt-test-messaging srt://40.71.22.29:4200?sndbuf=12058624&smoother=live&maxbw=156250 "" -msgsize 1456 -reply 0 -printmsg 0 -bitrate 1000000 -repeat 2575 -statsfreq 1 -statsfile _results/eunorth_useast-alg-busy_waiting-bitr-1.0Mbps-stats-snd-0.csv
```

Note regarding nakreport option: By default, `srt-test-messaging` sets `transtype`='file' to URI query. This turns off periodic NACK reports, but the default value for live mode is On. With this option turned off and live smoother, the FASTREXMIT mechanism will be used. Because in this test we send a limited number of messages, there might be a deadlock at the end of transmission when the sender relies on the periodic NACK reports. That's why we do not explicitly turn on periodic NACK reports with `nakreport=true` query option.

Option `nakreport=true` will turn off the FASTREXMIT mechanism on the sender, that starts resending packets if ACK was not received for a certain time. This forces extra load on the network, for file transmission it is better to wait for the loss report. 

#### Points of Analysis

* Loss ratio at each sending rate.
* Sending rate deviation on 10 ms intervals from average sending rate on 1 sec. In this test case the sending rate of SRT should be constant and should not depend on congestion control. Therefore it is a good point to analyze the accuracy.
* Actual bandwidth estimation of the link.


### <a name="filecc-loop-test"></a> 2. File CC Loop Test

The purpose of File CC Loop Test is to check the correctness and effectiveness of different congestion control algorithms implemented in SRT.

`srt-test-messaging` test application is used to produce data as fast as possible and send it over the network. Based on the test settings, the script calculates the number of packets need to be produced and streamed for `time_to_stream` seconds under assumption that available bandwidth `bandwidth` is known or estimated. These settings as well as message size, RTT, and smoother (Congestion Control) algorithm are specified within the `filecc-loop-test` section of config file. The script loops through the smoother algorithm if several values are defined. There is an option to loop through the message size, however, this not implemented as not wanted.

For example, in case of message size = 8MB = 8388608 bytes of payload, the data can be transferred with 5762 packets with maximum payload size 1456. The actual data size transmitted will be `8643000` bytes (`+3%`). With 1 Gbps there will be 14 packets per second (actual 10).

The script measures and returns an extra time spent by the application to transmit the generated amount of data packets.

#### Combinations Tested

* snd-quantity = 1
* snd-mode = parallel

#### Configuration and Command Line Examples for srt-test-messaging  Test Application

##### Receiver

* rcvbuf (Receiving buffer): 125000000 (attribute, hard-coded for now)
* sndbuf (Sending buffer): 125000000 (attribute, hard-coded for now)
* fc (Flow control): 60000 (attribute, hard-coded for now)
* smoother (Congestion Control algorithm): as specified in config file (attribute)
* msg_size (Message size): as specfied in config file (option)
* reply: 0 (option)
* printmsg: 0 (option)

An example of command line for `srt-test-messaging`, generated by the script:
```
./srt-test-messaging "srt://:4200?rcvbuf=125000000&sndbuf=125000000&fc=60000&smoother=file-v2" -msgsize 1456 -reply 0 -printmsg 0 -statsfreq 1 -statsfile _results/eunorth_useast-alg-busy_waiting-msg_size-1456-smoother-file-v2-stats-rcv.csv
```

##### Sender

* rcvbuf (Receiving buffer): 125000000 (attribute, hard-coded for now)
* sndbuf (Sending buffer): 125000000 (attribute, hard-coded for now)
* fc (Flow control): 60000 (attribute, hard-coded for now)
* smoother (Congestion Control algorithm): as specified in config file (attribute)
* msg_size (Message size): as specfied in config file (option)
* reply: 0 (option)
* printmsg: 0 (option)
* repeat (Number of messages to send): calculated as `time_to_stream` * `bandwidth` // `msg_size` (option)

An example of command line for `srt-test-messaging`, generated by the script:
```
./srt-test-messaging srt://40.71.22.29:4200?rcvbuf=125000000&sndbuf=125000000&fc=60000&smoother=file-v2 "" -msgsize 1456 -reply 0 -printmsg 0 -repeat 10302 -statsfreq 1 -statsfile _results/eunorth_useast-alg-busy_waiting-msg_size-1456-smoother-file-v2-stats-snd-0.csv
```

# Combined Tests Implemented

There are three combined tests implemented:
* [Combined Bandwidth and File CC Loop Test](#bw-filecc-loop-test),
* [Iterative Bandwidth Loop Test](#iterative-bw-loop-test),
* [Iterative File CC Loop Test](#iterative-filecc-loop-test).

They can be executed by means of running `perform_combined_test.py` script. Test name should be passed as an argument to a script as well as a config filepath. Usage
```
perform_combined_test.py [OPTIONS] 
[bw_filecc_loop_test|iterative_bw_loop_test|iterative_filecc_loop_test] CONFIG_FILEPATH
```

Use `--help` option in order to get the full list of options
```
Options:
  --snd-quantity INTEGER        Number of senders to start.  [default: 1]
  --snd-mode [serial|parallel]  Start senders concurrently or in parallel.
                                [default: parallel]
  --collect-stats               Collect SRT statistics.
  --run-tshark                  Run tshark.
  --results-dir TEXT            Directory to store results.  [default:
                                _results]
  --iterations INTEGER          Number of iterations. Applicable for iterative
                                tests only.  [default: 3]
  --interval INTEGER            Interval between iterations in seconds.
                                Applicable for iterative tests only.
                                [default: 30]
  --help                        Show this message and exit.
```

Config file example is the same as above.

## Combined Tests Description

### <a name="bw-filecc-loop-test"></a> Combined Bandwidth and File CC Loop Test

The test consists of two parts: the script first runs [Bandwidth Loop Test](#bandwidth-loop-test), and then after 10 seconds waiting runs [File CC Loop Test](#filecc-loop-test). Valid settings for both of tests should be specified within config file in appropriate tests sections.

### <a name="iterative-bw-loop-test"></a> Iterative Bandwidth Loop Test

The script runs [Bandwidth Loop Test](#bandwidth-loop-test) iteratively at defined time periods. Use `--iterations` option to set up the number of iterations and `--interval` option to set up the time period between iterations in seconds. The setting should be provided within `bw-loop-test` section of a config file.

### <a name="iterative-filecc-loop-test"></a> Iterative File CC Loop Test

The script runs [File CC Loop Test](#filecc-loop-test) iteratively at defined time periods. Use `--iterations` option to set up the number of iterations and `--interval` option to set up the time period between iterations in seconds. The setting should be provided within `filecc-loop-test` section of a config file.

# srt-xtransmit support

In order to run `srt-xtransmit` testing application please use `--app` option. Note that it is an experimental implementation and `srt-xtransmit` support has been tested primarily for File CC loop test and Iterative File CC loop test when running only 1 sender (the default number of senders).

For File CC loop test please use the command
```
python perform_test.py filecc_loop_test --app=srt-xtransmit --collect-stats --run-tshark --results-dir=_res config.ini 
```

For Iterative File CC loop test please run the command
```
python perform_combined_test.py iterative_filecc_loop_test --app=srt-xtransmit --collect-stats --run-tshark --results-dir=_res_iter --iterations=5 --interval=20 config.ini
```

Use `filecc-loop-test-xtransmit` config section in order to set message size, available bandwidth, and time to stream the data
```
[filecc-loop-test-xtransmit]
; Message size: 1456B, 4MB, 8MB
msg_size = 1456B
; Available bandwidth (bytes)
bandwidth = 125000000
; Time to stream (s).
time_to_stream = 20
```