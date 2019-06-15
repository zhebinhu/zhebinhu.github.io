---
title: CAS 原理和缺陷
tags: Java
toc: true
date: 2018-09-03 20:21:30
---
<!--more-->
JDK1.6 以后 JVM 对 synchronize 锁机制作了不少优化，加入了偏向锁和自旋锁，在锁的底层实现中或多或少的都借助了 CAS 操作，其实 Java 中 java.util.concurrent 包的实现也是差不多建立在 CAS 之上，可见 CAS 在 Java 同步领域的重要性。

CAS 是 Compare and Swap 的简写形式，可翻译为：比较并交换。用于在硬件层面上提供**原子性**操作。其实现方式是基于硬件平台的汇编指令，就是说 CAS 是靠硬件实现的，JVM 只是封装了汇编调用。比较是否和给定的数值一致，如果一致则修改，不一致则不修改。

## CAS 案例分析

AtomicInteger 的原子特性就是 CAS 机制的典型使用场景。 其相关的源码片段如下：
```java
private volatile int value;  
  
public final int get() {  
        return value;  
}  
  
public final int incrementAndGet() {  
    for (;;) {  
        int current = get();  
        int next = current + 1;  
        if (compareAndSet(current, next))  
            return next;  
    }  
}  
  
public final boolean compareAndSet(int expect, int update) {     
    return unsafe.compareAndSwapInt(this, valueOffset, expect, update);  
}  
```
AtomicInteger 在没有锁的机制下借助 volatile 原语，保证了线程间的数据是可见的（共享的）。其 get() 方法可以获取最新的内存中的值。

在 incrementAndGet() 的操作中，使用了 CAS 操作，每次从内存中读取最新的数据然后将此数据+1，最终写入内存时，先比较内存中最新的值，同累加之前读出来的值是否一致，不一致则写失败，循环重试直到成功为止。

compareAndSet 的具体实现调用了 unsafe 类的 compareAndSwapInt 方法，它其实是一个 Java Native Interface（简称 JNI）java 本地方法，会根据不同的 JDK 环境调用不同平台的对应 C 实现，下面以 windows 操作系统，X86 处理器的实现为例，这个本地方法在 openjdk 中依次调用的 c++代码为：unsafe.cpp，atomic.cpp 和 atomic_windows_x86.inline.hpp，它的实现代码存在于：openjdk7\hotspot\src\os_cpu\windows_x86\vm\atomic_windows_x86.inline.hpp，下面是相关的代码片段：
```C++
// Adding a lock prefix to an instruction on MP machine  
// VC++ doesn't like the lock prefix to be on a single line  
// so we can't insert a label after the lock prefix.  
// By emitting a lock prefix, we can define a label after it.  
#define LOCK_IF_MP(mp) __asm cmp mp, 0  \  
                       __asm je L0      \  
                       __asm _emit 0xF0 \  
                       __asm L0:  
  
inline jint     Atomic::cmpxchg    (jint     exchange_value, volatile jint*     dest, jint     compare_value) {  
  // alternative for InterlockedCompareExchange  
  int mp = os::is_MP();  
  __asm {  
    mov edx, dest  
    mov ecx, exchange_value  
    mov eax, compare_value  
    LOCK_IF_MP(mp)  
    cmpxchg dword ptr [edx], ecx  
  }  
}  
```
由上面源代码可见在该平台的处理器上 CAS 通过指令 cmpxchg（就是 x86 的比较并交换指令）实现，并且程序会根据当前处理器是否是多处理器 (is_MP) 来决定是否为 cmpxchg 指令添加 lock 前缀 (LOCK_IF_MP)，如果是单核处理器则省略 lock 前缀 (单处理器自身会维护单处理器内的顺序一致性，不需要 lock 前缀提供的内存屏障效果 (而在 JDK9 中，已经忽略了这种判断都会直接添加 lock 前缀，这或许是因为现代单核处理器几乎已经消亡)。关于 Lock 前缀指令：
- Lock 前缀指令可以通过对总线或者处理器内部缓存加锁，使得其他处理器无法读写该指令要访问的内存区域，因此能保存指令执行的原子性。
- Lock 前缀指令将禁止该指令与之前和之后的读和写指令重排序。
- Lock 前缀指令将会把写缓冲区中的所有数据立即刷新到主内存中。

上面的第 1 点保证了 CAS 操作是一个原子操作，第 2 点和第 3 点所具有的内存屏障效果，保证了 CAS 同时具有 volatile 读和 volatile 写的内存语义（不过一般还是认为 CAS 只具有原子性而不具有可见性，因为底层的处理器平台可能不同）。

**关于总线锁定和缓存锁定**
> 1、早期的处理器只支持通过总线锁保证原子性。所谓总线锁就是使用处理器提供的一个 LOCK＃信号，当一个处理器在总线上输出此信号时，其他处理器的请求将被阻塞住,那么该处理器可以独占使用共享内存。很显然，这会带来昂贵的开销。
2、缓存锁定是改进后的方案。在同一时刻我们只需保证对某个内存地址的操作是原子性即可，但总线锁定把 CPU 和内存之间通信锁住了，这使得锁定期间，其他处理器不能操作其他内存地址的数据，所以总线锁定的开销比较大，最近的处理器在某些场合下使用缓存锁定代替总线锁定来进行优化。缓存锁定是指当两个 CPU 的缓存行同时指向一片内存区域时，如果 A CPU 希望对该内存区域进行修改并使用了缓存锁定，那么 B CPU 将无法访问自己缓存中相应的缓存行，自然也没法访问对应的内存区域，这样就 A CPU 就实现了独享内存。
　
但是有两种情况下处理器不会使用缓存锁定。第一种情况是：当操作的数据不能被缓存在处理器内部，或操作的数据跨多个缓存行（cache line），则处理器会调用总线锁定。第二种情况是：有些处理器不支持缓存锁定。对于 Inter486 和奔腾处理器，就算锁定的内存区域在处理器的缓存行中也会调用总线锁定。


**关于同样使用 Lock 前缀的 volatile 却无法保证原子性**
> volatile 和 cas 都是基于 lock 前缀实现，但 volatile 却无法保证原子性这是因为：Lock 前缀只能保证缓存一致性，但不能保证寄存器中数据的一致性，如果指令在 lock 的缓存刷新生效之前把数据写入了寄存器，那么寄存器中的数据不会因此失效而是继续被使用，就好像数据库中的事务执行失败却没有回滚，原子性就被破坏了。以被 volatile 修饰的 i 作 i++为例，实际上分为 4 个步骤：
mov　　　　 0xc(%r10),%r8d ; 把 i 的值赋给寄存器
inc　　　　　%r8d　　　　　 ; 寄存器的值+1
mov　　　　 %r8d,0xc(%r10) ; 把寄存器的值写回
lock addl　　$0x0,(%rsp)　　; 内存屏障，禁止指令重排序，并同步所有缓存
　
如果两个线程 AB 同时把 i 读进自己的寄存器，此时 B 线程等待，A 线程继续工作，把 i++后放回内存。按照原子性的性质，此时 B 应该回滚，重新从内存中读取 i，但因为此时 i 已经拷贝到寄存器中，所以 B 线程会继续运行，原子性被破坏。
　
而 cas 没有这个问题，因为 cas 操作对应指令只有一个：
lock cmpxchg dword ptr [edx], ecx ;
　
该指令确保了直接从内存拿数据（ptr [edx]），然后放回内存这一系列操作都在 lock 状态下，所以是原子性的。
　
总结：volatile 之所以不是原子性的原因是 jvm 对 volatile 语义的实现只是在 volatile 写后面加一个内存屏障，而内存屏障前的操作不在 lock 状态下，这些操作可能会把数据放入寄存器从而导致无法有效同步；cas 能保证原子性是因为 cas 指令只有一个，这个指令从头到尾都是在 lock 状态下而且从内存到内存，所以它是原子性的。

## CAS 缺陷

1、**ABA 问题**。因为 CAS 需要在操作值的时候检查下值有没有发生变化，如果没有发生变化则更新，但是如果一个值原来是 A，变成了 B，又变成了 A，那么使用 CAS 进行检查时会发现它的值没有发生变化，但是实际上却变化了。ABA 问题的解决思路就是使用版本号。在变量前面追加上版本号，每次变量更新的时候把版本号加一，那么 A－B－A 就会变成 1A - 2B－3A。

从 Java1.5 开始 JDK 的 atomic 包里提供了一个类 AtomicStampedReference 来解决 ABA 问题。这个类的 compareAndSet 方法作用是首先检查当前引用是否等于预期引用，并且当前标志是否等于预期标志，如果全部相等，则以原子方式将该引用和该标志的值设置为给定的更新值。

2、**循环时间长开销大**。自旋 CAS 如果长时间不成功，会给 CPU 带来非常大的执行开销。如果 JVM 能支持处理器提供的 pause 指令那么效率会有一定的提升，pause 指令有两个作用，第一它可以延迟流水线执行指令（de-pipeline），使 CPU 不会消耗过多的执行资源，延迟的时间取决于具体实现的版本，在一些处理器上延迟时间是零。第二它可以避免在退出循环的时候因内存顺序冲突（memory order violation）而引起 CPU 流水线被清空（CPU pipeline flush），从而提高 CPU 的执行效率。 

3、**只能保证一个共享变量的原子操作**。当对一个共享变量执行操作时，我们可以使用循环 CAS 的方式来保证原子操作，但是对多个共享变量操作时，循环 CAS 就无法保证操作的原子性，这个时候就可以用锁，或者有一个取巧的办法，就是把多个共享变量合并成一个共享变量来操作。比如有两个共享变量 i＝2，j=a，合并一下 ij=2a，然后用 CAS 来操作 ij。从 Java1.5 开始 JDK 提供了 AtomicReference 类来保证引用对象之间的原子性，你可以把多个变量放在一个对象里来进行 CAS 操作。 

4、**总线风暴带来的本地延迟**。在多处理架构中，所有处理器会共享一条总线，靠此总线连接主存，每个处理器核心都有自己的高速缓存，各核相对于 BUS 对称分布，这种结构称为“对称多处理器”即 SMP。当主存中的数据同时存在于多个处理器高速缓存的时候，某一个处理器的高速缓存中相应的数据更新之后，会通过总线使其它处理器的高速缓存中相应的数据失效，从而使其重新通过总线从主存中加载最新的数据，大家通过总线的来回通信称为“Cache 一致性流量”，因为总线被设计为固定的“通信能力”，如果 Cache 一致性流量过大，总线将成为瓶颈。而 CAS 恰好会导致 Cache 一致性流量，如果有很多线程都共享同一个对象，当某个核心 CAS 成功时必然会引起总线风暴，这就是所谓的本地延迟。而偏向锁就是为了消除 CAS，降低 Cache 一致性流量。

　
**关于偏向锁如何消除 CAS**
> 试想这样一种情况：线程 A：申请锁 - 执行临界区代码 - 释放锁 - 申请锁 - 执行临界区代码 - 释放锁。锁的申请和释放都会执行 CAS，一共执行 4 次 CAS。而在偏向锁中，线程 A：申请锁 - 执行临界区代码 - 比较对象头 - 执行临界区代码。只执行了 1 次 CAS。

**关于总线风暴**
> 其实也不是所有的 CAS 都会导致总线风暴，这跟 Cache 一致性协议有关，具体参考：http://blogs.oracle.com/dave/entry/biased_locking_in_hotspot
另外与 SMP 对应还有非对称多处理器架构，现在主要应用在一些高端处理器上，主要特点是没有总线，没有公用主存，每个 Core 有自己的内存。