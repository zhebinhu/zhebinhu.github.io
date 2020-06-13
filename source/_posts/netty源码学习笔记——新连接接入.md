---
title: Netty 源码浅析——新连接接入
tags: 
	- Netty
toc: true
date: 2019-10-03 14:33:27
---
上一章讲了 Netty 中的 NioEventLoop，我们了解到 NioEventLoop 有两个启动时机，一个是在服务器端口绑定的时候，会启动 bossGroup 中的 NioEventLoop ，而另一个则是在新连接接入的时候启动 workGroup 中的  NioEventLoop。前两章我们了解了服务端端口绑定的过程，那么这一章我们就来阅读一下新连接接入相关的代码。

新连接接入一共可分为四个步骤：
- 检测新连接
- 创建 NioSocketChannel
- 分配线程及注册 Selector
- 向 Selector 注册读事件

接下来我们就逐一来看每个阶段的工作流程。

## 检测新连接

上一章我们了解到 NioEventLoop 内部是一个 for 循环，不停地做三件事：检测 IO 事件->处理 IO 事件->处理异步任务队列。我们看到在第二步处理 IO 事件中 Netty 对 Selector 轮询到的事件分门别类地进行了处理，这其中就包括新连接接入事件。新连接是由 bossGroup 的 NioEventLoop 检测到的，相关的代码在 `processSelectedKey()` 中：
```java
NioEventLoop
private void processSelectedKey(SelectionKey k, AbstractNioChannel ch) {
    // 获取 Channel 的 unsafe
    final AbstractNioChannel.NioUnsafe unsafe = ch.unsafe();
    if (!k.isValid()) {
        //...
        // 连接无效，关闭连接
        unsafe.close(unsafe.voidPromise());
        return;
    }

    try {
        int readyOps = k.readyOps();
        // 处理 OP_CONNECT 事件
        if ((readyOps & SelectionKey.OP_CONNECT) != 0) {
            int ops = k.interestOps();
            ops &= ~SelectionKey.OP_CONNECT;
            k.interestOps(ops);

            unsafe.finishConnect();
        }
        // 处理 OP_WRITE 事件
        if ((readyOps & SelectionKey.OP_WRITE) != 0) {
            ch.unsafe().forceFlush();
        }
        // 处理 OP_READ 和 OP_ACCEPT 事件
        if ((readyOps & (SelectionKey.OP_READ | SelectionKey.OP_ACCEPT)) != 0 || readyOps == 0) {
            unsafe.read();
        }
    } catch (CancelledKeyException ignored) {
        // 出错，关闭连接
        unsafe.close(unsafe.voidPromise());
    }
}
```
我们看到在整个方法的开头，NioEventLoop 获取到了 Channel 的 unsafe 组件，然后在处理 OP_ACCEPT 事件时调用到了 unsafe 的 `read()` 方法，我们进入到 `read()` 方法体内：
```java
NioMessageUnsafe
private final List<Object> readBuf = new ArrayList<Object>();
public void read() {
    //...
    // 获取 Channel 的 pipeline
    final ChannelPipeline pipeline = pipeline();
    // 用于控制速率
    final RecvByteBufAllocator.Handle allocHandle = unsafe().recvBufAllocHandle();
    //...
    do {
        // 通过一个 while 循环不断读取 buffer 中的数据
        int localRead = doReadMessages(readBuf);
        if (localRead == 0) {
            break;
        }
        if (localRead < 0) {
            closed = true;
            break;
        }
        allocHandle.incMessagesRead(localRead);
    } while (allocHandle.continueReading());
    int size = readBuf.size();
    // 传播读取事件
    for (int i = 0; i < size; i ++) {
        pipeline.fireChannelRead(readBuf.get(i));
    }
    readBuf.clear();
    // 传播读取完毕事件
    pipeline.fireChannelReadComplete();
    //...
}
```
这里省略了一些非关键的代码，首先我们看到 `read()` 方法中拿到了 Channel 的 pipeline 和一个 RecvByteBufAllocator.Handle（用于控制速率，后面会分析）；接下来会通过一个 while 循环不断把消息存到一个 list 中（我们之后会看到服务端 Channel 这里读到的消息就等于新连接）；最后把读到的消息传播到 pipeline，然后清理容器，传播读取完毕事件。

大致的过程就是这些，我们先来看一下 `doReadMessages()` 这个方法，这个方法在服务端 Channel 和客户端 Channel 里面的实现不一样的。这也很好理解，因为不同的事件组关心的事件是不一样的，对于服务端 Channel 来说关心的是新连接的接入，所以 `doReadMessages()` 读到的就是新连接；而对客户端 Channel 来说关心的是有没有新的数据，所以 `doReadMessages()` 读到的是数据流。

我们在这里进入 NioServerSocketChannel 的 `doReadMessages()` 方法：
```java
NioServerSocketChannel
protected int doReadMessages(List<Object> buf) throws Exception {
    // 拿到新连接 
    SocketChannel ch = SocketUtils.accept(javaChannel());

    try {
        if (ch != null) {
            // 创建 NioSocketChannel
            buf.add(new NioSocketChannel(this, ch));
            // 返回 1 表示收到一条新连接
            return 1;
        }
    } catch (Throwable t) {
        //...
    }
    // 返回 0 表示没收到新连接
    return 0;
}
```
我们看到在 `doReadMessages()` 方法里面拿到了新连接并且把它包装成了 Netty 里面的 NioSocketChannel 类型。具体过程我们下一节再来分析，这里我们关注一下返回值，返回的是拿到新连接的数量，1 表示拿到了新连接，0 表示没有拿到。然后让我们返回外层的 do-while 循环：
```java
do {
    // 通过一个 while 循环不断读取 buffer 中的数据
    int localRead = doReadMessages(readBuf);
    // 没拿到连接，直接跳出
    if (localRead == 0) {
        break;
    }
    if (localRead < 0) {
        closed = true;
        break;
    }
    allocHandle.incMessagesRead(localRead);
} while (allocHandle.continueReading());
```
我们看到 while 循环的条件是 `allocHandle.continueReading()`，而在此之前会做一个 `allocHandle.incMessagesRead(localRead)` 的操作，allocHandle 我们一开始说过，是用于控制新连接接入速率的，那么具体是怎么控制的呢，我们进入它的代码：
```java
DefaultMaxMessagesRecvByteBufAllocator
public final void incMessagesRead(int amt) {
    // totalMessages 表示接收的新连接总数
    totalMessages += amt;
}

public boolean continueReading(UncheckedBooleanSupplier maybeMoreDataSupplier) {
    return config.isAutoRead() 
           && (!respectMaybeMoreData || maybeMoreDataSupplier.get()) 
           // 核心，检查接收的新连接总数是否小于阈值，阈值一般为 16
           && totalMessages < maxMessagePerRead
           && totalBytesRead > 0;
}
```
我们看到有一个 maxMessagePerRead 的参数控制了每次调用 `read()` 方法接收的新连接数量，如果超过这个数量，会停止接收连接。

检测新连接的代码就到这里，我们知道了检测新连接发生在 bossGroup 的 NioEventLoop 循环中，当 NioEventLoop 底层的 Selector 接收到 OP_ACCEPT 事件后，会调用服务端 Channel 的 `unsafe.read()` 方法获取新连接。每次调用 `read()` 方法获取的新连接有一个上限，默认是 16。

## 创建 NioSocketChannel

检测到新连接之后就是拿到新连接，然后把它封装成 Netty 的 Channel，让我们回到 NioServerSocketChannel 的 `doReadMessages()` 方法中：
```java
NioServerSocketChannel
protected int doReadMessages(List<Object> buf) throws Exception {
    // 拿到新连接 
    SocketChannel ch = javaChannel().accept();

    try {
        if (ch != null) {
            // 创建 NioSocketChannel
            buf.add(new NioSocketChannel(this, ch));
            // 返回 1 表示收到一条新连接
            return 1;
        }
    } catch (Throwable t) {
        //...
    }
    // 返回 0 表示没收到新连接
    return 0;
}
```
首先通过调用 jdk 底层的 `accept()` 方法拿到新连接，由于检测新连接时已经检测到有 OP_ACCEPT 事件发生，因此，这里的 `accept()` 方法是立即返回的，返回 jdk 底层 nio 创建的一条 Channel。然后 Netty 将 jdk 的 SocketChannel 封装成自定义的 NioSocketChannel，加入到 list 里面，这样外层就可以遍历该 list，做后续处理。

我们知道服务端 Channel 在创建过程中会创建 pipeline、unsafe 等一系列组件，那么客户端 Channel 呢？我们看一下 `new NioSocketChannel` 的构造过程：
```java
NioSocketChannel
public NioSocketChannel(Channel parent, SocketChannel socket) {
    super(parent, socket);
    // TCP 参数配置类
    config = new NioSocketChannelConfig(this, socket.socket());
}

AbstractNioByteChannel
protected AbstractNioByteChannel(Channel parent, SelectableChannel ch) {
    // 传入 OP_READ 作为感兴趣事件
    super(parent, ch, SelectionKey.OP_READ);
}

AbstractNioChannel
protected AbstractNioChannel(Channel parent, SelectableChannel ch, int readInterestOp) {
    super(parent);
    this.ch = ch;
    // 设置感兴趣事件
    this.readInterestOp = readInterestOp;
    try {
        // 设置非阻塞
        ch.configureBlocking(false);
    } catch (IOException e) {
        //... 
    }
}

AbstractChannel
protected AbstractChannel(Channel parent, ChannelId id) {
    this.parent = parent;
    // 创建唯一 id
    this.id = newId();
    // 创建 unsafe
    unsafe = newUnsafe();
    // 创建 pipeline
    pipeline = newChannelPipeline();
}
```
我们看到过程和服务端 Channel 几乎一样，同样会创建 unsafe、pipeline 等组件，也同样会设置为非阻塞。唯一不同之处在于客户端 Channel 传入的感兴趣事件是 OP_ACCEPT，而服务端 Channel 传入的感兴趣事件是 OP_READ。

到这里新连接就创建完成了，概括一下就是先通过 jdk 底层的 `accept()` 拿到 jdk 底层的 Channel，然后把它封装成 Netty 自己的 Channel，在封装的过程中会创建 pipeline、unsafe 等组件。

## 分配线程及注册 Selector

拿到新连接之后就要分配线程及注册 Selector。我们在服务端启动过程中在服务端 Channel 的 pipeline 中添加了一个处理器 ServerBootstrapAcceptor，这是一个专门负责新连接接入的处理器。当服务端 Channel 拿到新连接之后，会触发 pipeline 上的 channelRead 事件：
```java
NioMessageUnsafe
public void read() {
    //...
    for (int i = 0; i < size; i ++) {
        readPending = false;
        // 触发 channelRead 事件
        pipeline.fireChannelRead(readBuf.get(i));
    }
    //...
}

```
最终通过 head->unsafe->ServerBootstrapAcceptor 的调用链，调用到 ServerBootstrapAcceptor 的 `channelRead()` 方法：
```java
ServerBootstrapAcceptor
public void channelRead(ChannelHandlerContext ctx, Object msg) {
    // 把 msg 强转成 Channel
    final Channel child = (Channel) msg;
    // 在客户端 Channel 上添加 childHandler，childHandler 是用户代码通过 `childHandler()` 指定的
    child.pipeline().addLast(childHandler);
    // 设置 option
    setChannelOptions(child, childOptions, logger);
    // 设置 attr
    for (Entry<AttributeKey<?>, Object> e: childAttrs) {
        child.attr((AttributeKey<Object>) e.getKey()).set(e.getValue());
    }

    try {
        // 注册客户端 Channel
        childGroup.register(child).addListener(new ChannelFutureListener() {
            @Override
            public void operationComplete(ChannelFuture future) throws Exception {
                if (!future.isSuccess()) {
                    forceClose(child, future.cause());
                }
            }
        });
    } catch (Throwable t) {
        forceClose(child, t);
    }
}
```
ServerBootstrapAcceptor 一上来就把 msg 强制转换为 Channel，这是因为 ServerBootstrapAcceptor 是一个特殊的处理器，只会绑定在服务端 Channel 上，而服务端 Channel 的 channelRead 事件只会在新连接接入时触发。

然后，拿到该 Channel，也就是我们上文刚创建好的 NioSocketChannel，将用户代码中的 childHandler 添加到它的 pipeline 中，这里的 childHandler 是我们在用户代码通过 `childHandler()` 指定的。

接着，设置 NioSocketChannel 对应的 attr 和 option，然后进入到 `childGroup.register(child)`，这里的 childGroup 就是我们在用户代码中设置的 workGroup。在 `register()` 方法中会为客户端 Channel 分配线程及注册 Selector：
```java
MultithreadEventLoopGroup.java
public ChannelFuture register(Channel channel) {
    // next() 方法会为 channel 分配线程
    return next().register(channel);
}
```
首先会通过 next() 方法为客户端 Channel 分配线程：
```java
MultithreadEventExecutorGroup
private final EventExecutorChooserFactory.EventExecutorChooser chooser;
public EventExecutor next() {
    // 通过线程选择器分配线程
    return chooser.next();
}
```
可以看到是通过线程选择器 chooser 来为客户端 Channel 分配线程的。关于 chooser 如何分配线程的部分我们已经在[服务端启动流程](http://huzb.me/2019/09/16/netty%E6%BA%90%E7%A0%81%E5%AD%A6%E4%B9%A0%E7%AC%94%E8%AE%B0%E2%80%94%E2%80%94%E6%9C%8D%E5%8A%A1%E5%99%A8%E5%90%AF%E5%8A%A8%E6%B5%81%E7%A8%8B/)中分析过了。客户端和服务端的线程分配过程是一模一样的。

拿到的线程是 NioEventLoop，之后会调用 NioEventLoop 的 `register()` 方法，实际上是代理到其父类 SingleThreadEventLoop 的 `register()` 方法：

```java
SingleThreadEventLoop
public ChannelFuture register(Channel channel) {
    return register(new DefaultChannelPromise(channel, this));
}
```

实际上这里的过程已经和服务端启动的过程一模一样了，详细步骤可以参考[服务端启动流程](http://huzb.me/2019/09/16/netty%E6%BA%90%E7%A0%81%E5%AD%A6%E4%B9%A0%E7%AC%94%E8%AE%B0%E2%80%94%E2%80%94%E6%9C%8D%E5%8A%A1%E5%99%A8%E5%90%AF%E5%8A%A8%E6%B5%81%E7%A8%8B/)这篇文章，我们直接跳到关键环节：

```java
AbstractNioChannel
private void register0(ChannelPromise promise) {
    boolean firstRegistration = neverRegistered;
    // 实际的注册流程
    doRegister();
    neverRegistered = false;
    registered = true;
    // 触发 HandlerAddedIfNeeded 事件
    pipeline.invokeHandlerAddedIfNeeded();

    safeSetSuccess(promise);
    // 触发 ChannelRegistered 事件
    pipeline.fireChannelRegistered();
    // 连接建立后会把连接置为 Active，这里为 true
    if (isActive()) {
        if (firstRegistration) {
            // 触发 ChannelActive 事件
            pipeline.fireChannelActive();
        } else if (config().isAutoRead()) {
            beginRead();
        }
    }
}
```
和服务端启动过程一样，先是调用 `doRegister()` 做真正的注册过程，如下：
```java
AbstractNioChannel
protected void doRegister() throws Exception {
    boolean selected = false;
    for (;;) {
        try {
            // 绑定到 jdk 底层的 Selector 上
            selectionKey = javaChannel().register(eventLoop().selector, 0, this);
            return;
        } catch (CancelledKeyException e) {
            //...
        }
    }
}
```
调用 jdk 底层的 `register()` 进行注册，并把 Netty 的 Channel 作为 attachment 传入，以便在轮询到事件的时候带出来。这部分在服务端启动过程中讲过，这里就不详细讲述了。

注册到 Selector 上之后，客户端 Channel 会触发 HandlerAddedIfNeeded 事件和 ChannelRegistered 事件，其中 HandlerAddedIfNeeded 事件会调用到 ChannelInitializer 的 handlerAdded 方法。ChannelInitializer 是一个调用一次就会把自己从 pipeline 中移除，用于初始化 Channel 的特殊处理器，这个处理器我们也在服务端启动过程中详细讲过了。

## 注册读事件

接下来会有一个和服务端不一样的地方，当我们把服务端 Channel 注册到 Selector 上时，此时连接还要绑定端口，因此服务端中的 `isActive()` 返回 false，但客户端 Channel 不需要绑定端口，因此客户端 Channel 的 `isActive()` 返回 true，直接触发 ChannelActive 事件。和服务端 Channel 一样，ChannelActive 也会传播到 pipeline 中的 head 节点，head 节点在这里会把 readInterestOp 对应的事件注册到 Selector，结合前面的创建过程，这里其实是把 OP_READ 事件注册到 Selector 中去了;
```java
AbstractNioChannel
protected void doBeginRead() throws Exception {
    final SelectionKey selectionKey = this.selectionKey;
    if (!selectionKey.isValid()) {
        return;
    }

    readPending = true;

    final int interestOps = selectionKey.interestOps();
    if ((interestOps & readInterestOp) == 0) {
        // 把 OP_READ 事件添加到服务端 Channel 的感兴趣事件集合
        selectionKey.interestOps(interestOps | readInterestOp); 
    }
}
```
这样客户端 Channel 就开始监听读事件。到此，新连接接入的过程结束了。

## 总结

我们以 tips 的形式来总结一下新连接接入的流程：
- Netty 在 bossGroup 的 NioEventLoop 中轮询到 OP_ACCEPT 事件
- 调用 jdk 底层的 `accept()` 方法获取 jdk 底层的 Channel，然后把它封装成 Netty 的 NioSocketChannel 并创建 pipeline、 unsafe 等一系列组件
- 通过服务端 Channel 的一个特殊处理器 ServerBootstrapAcceptor，为新的 Channel 添加 childHandler、option、attr 等一系列参数，并调用 workGroup 的 `register()` 方法注册新连接
- workGroup 会通过自己的线程选择器 chooser 为新连接分配一个 NioEventLoop，并把新连接注册到 NioEventLoop 的 Selector 上去
- 通过传播 ChannelActive 为新连接在 Selector 上注册读事件，至此，新连接可以正常读写数据


## 参考资料
[netty源码分析之新连接接入全解析](https://www.jianshu.com/p/0242b1d4dd21)