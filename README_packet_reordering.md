# test-packet-reordering

Script designed to evaluate packet reordering as per [RFC 4737 - Packet Reordering Metrics](https://tools.ietf.org/html/rfc4737).

The idea of the script is the following:

1. On a sender side, generate and send via stdin `k` packets of `Payload Size = 1316 bytes` with the following payload structure
```
|<------------------- Payload Size ------------------------>|
|<-- SrcByte -->|<-- SrcTime -->|                           |
|    4 bytes    |    4 bytes    |                           |
+---+---+---+---+---+---+---+---+---+---+---+---+---+   +---+
| x | x | x | x | x | x | x | x | 9 |10 |...|...|...|...| 0 |
+---+---+---+---+---+---+---+---+---+---+---+---+---+   +---+
                                                          |
          0 byte at the end indicates the end of payload__/        
```
where `SrcByte` -- Packet Sequence Number applied at the source,
in units of payload bytes,
`SrcTime` -- the time of packet emission from the source,
in units of payload bytes (not yet implemented).

2. On a receiver side, receive and read the data from stdout, then validate received packets for possible packet reordering, duplicates, sequence discontinuities and packet loss.

3. The pipeline is as follows: file://con {stdin of testing application} -> SRT -> file://con {stdout of testing application}.

The original idea is coming from the following [PR #663](https://github.com/Haivision/srt/pull/663).


# Metrics supported

## Type-P-Reordered-Ratio-Stream

Given a stream of packets sent from a source to a destination, the ratio of reordered packets in the sample is 

```
R = (Count of packets with Type-P-Reordered=TRUE) / ( L ) * 100
```

where `L` is the total number of packets received out of the `K` packets sent. Recall that identical copies (duplicates) have been removed, so L <= K.

Note 1: If duplicate packets (multiple non-corrupt copies) arrive at the destination, they MUST be noted, and only the first to arrive is considered for further analysis (copies would be declared reordered packets).  

Note 2: Let k be a positive integer equal to the number of packets sent. Let l be a non-negative integer representing the number of packets that were received out of the k packets sent. Note that there is no relationship between k and l: on one hand, losses can make l less than k; on the other hand, duplicates can make l greater than k.
   
# Getting Started

## Requirements

* python 3.6+
* SRT test application `srt-live-transmit` or `srt-test-live` built on both receiver and sender side

To install python libraries use:
```
pip install -r requirements_packet_reordering.txt
```


# Running the Script

Please use `--help` option in order to get the full list of available options and sub-commands.
```
Usage: test_packet_reordering.py [OPTIONS] COMMAND [ARGS]...

Options:
  --debug / --no-debug
  --help                Show this message and exit.

Commands:
  re-receiver
  re-sender
  receiver
  sender

```

`re-receiver` and `re-sender` sub-commands are designed for Redundancy Feature testing and should be used with `srt-test-live` testing application.

`receiver` and `sender` sub-commands are designed for the other use caes and should be used with `srt-live-transmit` testing application.

Please take into consideration that a receiver should be started first, then as soon as you get the following message in a terminal
```
2019-09-02 15:39:14,052 [INFO] Please start a sender with 1) the same value of n or duration and bitrate, 2) with the same attributes ...
```
you can start a sender and a transmission via SRT will happen. Note, that both receiver and sender should be started with 1) the same values of n or duration and bitrate, 2) the same attributes. See examples below.

Important to know: Once the transmission is finished, both sender and receiver will be stopped. However there is an opportunity for receiver to hang in case not all the sent packets are received. As of now, use `Ctrl-C` to interrupt the script.

Important to consider that: 1) receiver mode = listener, sender mode = caller; 2) network impairements should be introduced properly, e.g., if receiver is started at Endpoint A and sender - at Endpoint B, than network impairements like packet reordering, delay, etc. should be introduced at Endpoint B.

Use `--help` to get the list of available options for a particular sub-command
```
python test_packet_reordering.py re-receiver --help
```

## Examples - Redundancy Feature Testing

### Locally

```
python test_packet_reordering.py --debug re-receiver --duration 180 --bitrate 10 --attrs "latency=200&sndbuf=125000000&rcvbuf=125000000&fc=60000" ../srt/srt-ethouris/_build/srt-test-live
```
```
python test_packet_reordering.py --debug re-sender --duration 180 --bitrate 10 --attrs "latency=200&sndbuf=125000000&rcvbuf=125000000&fc=60000" --node 127.0.0.1:4200 ../srt/srt-ethouris/_build/srt-test-live
```

### On two machines

```
python test_packet_reordering.py --debug re-receiver --duration 180 --bitrate 10 --attrs "latency=200&sndbuf=125000000&rcvbuf=125000000&fc=60000" ../srt/srt-ethouris/_build/srt-test-live
```
```
python test_packet_reordering.py --debug re-sender --duration 180 --bitrate 10 --attrs "latency=200&sndbuf=125000000&rcvbuf=125000000&fc=60000" --node 192.168.2.1:4200 --node 192.168.3.1:4200 ../srt/srt-ethouris/_build/srt-test-live
```

Use `--ll`, `--lf` options to get logs from test-application for the purposes of debugging. In this case, make sure that `srt-test-live` application has been built with `-DENABLE_HEAVY_LOGGING=ON` enabled. Important to know: logs capturing affects the speed of data packets receiving which may result in a pretty big sequence number difference between received and sent packets (more than 1000 when usually it is around 100-200). It also affects the process of data receiving and results in appearance of sequence discontinuities and lost packets. It is expected behaviour and most probably related to the absence of free space in receiving buffer while producing log messages by the protocol. 

As of now `stderr` of test application is not captured, so you can see the messages in a terminal as well as script's log messages. In order to capture all these messages to a file add `2>&1 | tee filepath` postfix to a command.

# Notes

## Note 1 - Receiver Stop Condition

Let `k` be a positive integer equal to the number of packets sent. Let `l` be a non-negative integer representing the number of packets that were received out of the `k` packets sent. Note that there is no relationship between `k` and `l`: on one hand, losses can make `l` less than `k`; on the other hand, duplicates can make `l` greater than `k`.

As of now, we will stop the receiver once `k` packets are received, as a result there would be no chance to get all the possible duplicated packets. Some percentage of `k`, let's say 5%, can be introduced to improve this.

## Note 2 - SRT Overhead

According to measurements performed on a local host, the following overhead was mentioned:

| Bitrate, Mbit/s | Overhead, Mbit/s | Overhead, %  |
|-------------:   |----------------: | -----------: |
| 1               | 0.125            | 12.5         |
| 2               | 0.150            | 7.5          |
| 3               | 0.180            | 6            |
| 5               | 0.250            | 5            |
| 7               | 0.300            | 4.3          |
| 10              | 0.400            | 4            |
| 20              | 0.650            | 3.25         |


Taking into consideration that packet payload size = 1316 bytes, overhead should be approximately 3.19% (28 + 16 = 42 bytes). It would be good to additionally investigate this taking SRT stats and WireShark dumps: might probably, the higher overhead at lower bitrates is related to packet retransmission. According to specification, in case of no retransmission SRT overhead should be greater than 100 kbit/s. 

The measurements were performed using the following commands:
```
venv/bin/python script_redundancy.py --debug re-receiver --duration=60 --bitrate=1 ../srt/srt-ethouris/_build/srt-test-live
```
```
venv/bin/python script_redundancy.py --debug re-sender --node=127.0.0.1:4200 --duration=60 --bitrate=1 ../srt/srt-ethouris/_build/srt-test-live
```

The traffic was measured using `iptraf` tool.

# ToDo

* If possible speed up data packets receiving at a receiver side,
* Integrate the script in the CI/CD pipeline, [PR #663](https://github.com/Haivision/srt/pull/663) to start with,
* Implement SrcTime (the time of packet emission from the source) inserted in a packet payload in order to be able to calculate DstTime, Delay, LateTime and other metrics related to sending and receiving packet times as per [RFC 4737 - Packet Reordering Metrics](https://tools.ietf.org/html/rfc4737),
* Implement n-reordering metric calculation as per [Section 5 of RFC 4737  - Packet Reordering Metrics](https://tools.ietf.org/html/rfc4737#section-5),
* Improve receiver stop condition in order to introduce some persentage of `k` packets to be able to receive all the possible duplicated packets, where `k` is the number of packets sent by sender,
* Investigate the case with high overhead at lower bitrates.