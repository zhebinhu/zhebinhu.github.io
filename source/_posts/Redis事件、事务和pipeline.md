---
title: Redis 事件、事务和 pipeline
tags: Redis
toc: true
date: 2019-02-12 19:34:57
---
<!--more-->
本文介绍了 Redis 中事件的类型和事件的调度与执行，以及对批量事件处理的两种方式：事务和 pipeline。

## 一、事件

Redis 服务器是一个事件驱动程序。Redis 的事件有两类：
- 文件事件：服务器通过套接字与客户端连接，文件事件就是服务器对套接字操作的抽象。
- 时间事件：服务器对定时操作的抽象。

### 文件事件

Redis 包装了底层的 select、epoll 等来实现自己的网络事件处理器。它使用 I/O 多路复用程序来同时监听多个套接字，并将到达的事件传送给文件事件分派器，分派器会根据套接字产生的事件类型调用相应的事件处理器。

<img src="./Redis 事件、事务和 pipeline/文件事件分派器.png"/>

### 时间事件

服务器有一些操作需要在给定的时间点执行，时间事件是对这类定时操作的抽象。

时间事件又分为：
- 定时事件：是让一段程序在指定的时间之内执行一次；
- 周期性事件：是让一段程序每隔指定时间就执行一次。

时间事件中的属性 when 会记录下次执行的时间，周期性事件在执行后会更新 when 的值，而定时事件会被删除。

Redis 将所有时间事件都放在一个无序链表中，由时间事件执行器通过遍历整个链表查找出已到达的时间事件，并调用相应的事件处理器。

### 事件的调度与执行

服务器需要不断监听文件事件的套接字才能得到待处理的文件事件，但是不能一直监听，否则时间事件无法在规定的时间内执行，因此监听时间应该根据距离现在最近的时间事件来决定。

事件调度与执行由 aeProcessEvents 函数负责，伪代码如下：
```python
def aeProcessEvents():
    # 获取到达时间离当前时间最接近的时间事件
    time_event = aeSearchNearestTimer()
    # 计算最接近的时间事件距离到达还有多少毫秒
    remaind_ms = time_event.when - unix_ts_now()
    # 如果事件已到达，那么 remaind_ms 的值可能为负数，将它设为 0
    if remaind_ms < 0:
        remaind_ms = 0
    # 根据 remaind_ms 的值，创建 timeval
    timeval = create_timeval_with_ms(remaind_ms)
    # 阻塞并等待文件事件产生，最大阻塞时间由传入的 timeval 决定
    aeApiPoll(timeval)
    # 处理所有已产生的文件事件
    procesFileEvents()
    # 处理所有已到达的时间事件
    processTimeEvents()
```
将 aeProcessEvents 函数置于一个循环里面，加上初始化和清理函数，就构成了 Redis 服务器的主函数，伪代码如下：

```python
def main():
    # 初始化服务器
    init_server()
    # 一直处理事件，直到服务器关闭为止
    while server_is_not_shutdown():
        aeProcessEvents()
    # 服务器关闭，执行清理操作
    clean_server()
```
从事件处理的角度来看，服务器运行流程如下：

<img src="./Redis 事件、事务和 pipeline/事件的调度与执行.png"/>

## 二、事务

Redis 通过 MULTI、EXEC、WATCH 等命令来实现事务功能。事务提供了一种将多个命令请求打包，然后一次性、按顺序地执行多个命令的机制，并且在事务执行期间，服务器不会中断事务而改去执行其他客户端的命令请求，它会将事务中的所有命令都执行完毕，然后才去处理其他客户端的命令请求。

一个事务包括三个步骤：
- 事务开始：事务以 MULTI 开始，返回 OK 命令。
- 命令入队：每个事务命令成功进入队列后，返回 QUEUED。
- 事务执行：EXEC 执行事务。

Redis 不支持事务回滚功能，事务中的一个 Redis 命令执行失败以后，会继续执行后续的命令。

## 三、pipeline

多个命令被一次性发送给服务器，而不是一条一条发送，这种方式被称为流水线，它可以减少客户端与服务器之间的网络通信次数从而提升性能。

可以通过`redis-cli --pipe`的方式批量发送命令。如`cat commands.txt | redis-cli --pipe`，commands.txt 中的命令会被以 RESP 协议（这是一个 Redis 自行规定的协议，用于命令的批量执行）的格式发给服务器，服务器也会返回一个 RESP 格式的结果。

当然我们不用自己去实现这个协议，Jedis 为我们实现好了，我们可以很方便地调用：
```java
        Jedis jedis = new Jedis("localhost", 6379);
        //使用 pipeline
        Pipeline pipeline = jedis.pipelined();
        //删除 lists
        pipeline.del("lists");
        //循环添加 10000 个元素
        for(int i = 0; i < 10000; i++){
            pipeline.rpush("lists", i + "");
        }
        //执行
        pipeline.sync();
```


