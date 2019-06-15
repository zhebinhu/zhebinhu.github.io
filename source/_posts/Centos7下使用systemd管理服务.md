---

title: Centos7 下使用 systemd 管理服务
tags: Linux
toc: true

date: 2018-03-30 21:09:37

---
<!--more-->
Centos7 新增了 systemd 用于为系统的启动和管理提供一套完整的解决方案，以替代原先的系统管理器 system V init（SysVInit）。相比于 SysVInit，systemd 支持服务并行启动，从而使效率大大提高；同时它还具有日志管理、快速备份与恢复、挂载点管理等多种实用功能，是一套更完善的系统管理方案。服务器后端会经常有将 mysql、redis、nginx 等部件开机启动的需求，现在可以统一交给 Systemd 管理，方便许多。

## Systemd 概述

在 Linux 系统中，我们经常会遇到结尾为 'd' 的进程，比如 initd，mysqld。根据 Linux 惯例，字母‘d’是守护进程（daemon）的缩写。systemd 这个名字的含义，就是它是整个系统的守护进程。在 Centos7 中，它是系统的第一个进程（PID 等于 1），创建于系统启动的过程中，其他进程都是它的子进程。

<img src="./Centos7 下使用 systemd 管理服务/一号进程.png">

在 Centos7 中，系统的启动可以汇整成如下几个过程：

①、打开计算机电源，载入 BIOS 的硬件信息与进行自我测试，并依据设置取得第一个可开机的设备；
②、读取并执行第一个开机设备内 MBR 的 boot loader（亦即是 grub2，spfdisk 等程序）；
③、依据 boot loader 的设置载入 Kernel，Kernel 会开始侦测硬件与载入驱动程序；
④、在硬件驱动成功后，Kernel 会主动调用 systemd 程序，并以 default.target 流程开机；
　　1) systemd 执行 sysinit.target 初始化系统及 basic.target 准备操作系统；
　　2) systemd 启动 multi-user.target 下的本机与服务器服务；
　　3) systemd 执行 multi-user.target 下的/etc/rc.d/rc.local 文件；
　　4) systemd 执行 multi-user.target 下的 getty.target 及登录服务；
　　5) systemd 执行 graphical 需要的服务（图形化版本特有）

大概就是上面这样子了。你会发现 systemd 出现的频率很高，这是因为 systemd 负责了开机时所有的资源（unit）调度任务，操作系统只需要启动 systemd，剩下的 systemd 都会帮它处理。不仅如此，**事实上，systemd 扮演的就是一个资源管理者的角色，它最主要的功能就是准备软件执行的环境，包括系统的主机名称、网络设置、语系处理、文件系统格式及其他服务的启动等**。

## Systemd 的基本概念和操作

### 一、Unit

Systemd 可以管理所有系统资源。不同的资源统称为 Unit（单元）。systemd 将资源归纳为以下一些不同的类型。然而，systemd 正在快速发展，新功能不断增加。所以资源类型可能在不久的将来继续增加。
>Service unit：系统服务（最常见）
Target unit：多个 Unit 构成的一个组
Device Unit：硬件设备
Mount Unit：文件系统的挂载点
Automount Unit：自动挂载点
Path Unit：文件或路径
Scope Unit：不是由 Systemd 启动的外部进程
Slice Unit：进程组
Snapshot Unit：Systemd 快照，可以切回某个快照
Socket Unit：进程间通信的 socket
Swap Unit：swap 文件
Timer Unit：定时器

#### Unit 配置文件

每一个 unit 都有一个配置文件，配置文件一般存放在目录/usr/lib/systemd/system/，它会告诉 systemd 怎么启动这个 unit。配置文件的后缀名，就是该 unit 的种类，比如 sshd.socket。如果省略，systemd 默认后缀名为.service，所以 sshd 会被理解成 sshd.service。

<img src="./Centos7 下使用 systemd 管理服务/redis.service.png">

上图为我系统中 redis.service 配置文件的内容。它大致包含了这些信息：1）对这个资源的描述；2）所需的前置资源；3）实际执行此 service 的指令或脚本程序；4）实际停止此 service 的指令或脚本程序；5）该资源所在的组（target）。

unit 配置文件中常用的字段整理如下：

Unit 字段 | 参数意义说明
---- | ---
Description| 就是当我们使用```systemctl list-units```时，会输出给管理员看的简易说明。使用```systemctl status```输出的此服务的说明，也是这个字段。
After | 说明此 unit 是在哪个 daemon 启动之后才启动的意思。基本上仅是说明服务启动的顺序而已，并没有强制要求里头的服务一定要启动后此 unit 才能启动。
Before | 与 After 的意义相反，是在什么服务启动前最好启动这个服务的意思。不过这仅是规范服务启动的顺序，并非强制要求的意思。
Requires| 明确地定义此 unit 需要在哪个 daemon 启动后才能够启动。如果在此项设置的前导服务没有启动，那么此 unit 就不会被启动。
Wants　　　　　　　　| 表示这个 unit 之后最好还要启动什么服务比较好的意思，不过并没有明确的规范。主要的目的是希望创建让使用者比较好操作的环境。因此，这个 Wants 后面接的服务如果没有启动，其实不会影响到这个 unit 本身。
Conflicts | 代表冲突的服务。表示这个项目后面接的服务如果有启动，那么我们这个 unit 本身就不能启动！我们 unit 有启动，则此项目后的服务就不能启动！是一种冲突性的检查。

Service 字段（service 特有） | 参数意义说明
---- | ---
Type | Type 字段定义启动类型。它可以设置的值如下：```simple（默认值）```：ExecStart 字段启动的进程为主进程。```forking```：ExecStart 字段将以 fork() 方式启动，此时父进程将会退出，子进程将成为主进程。```oneshot```：类似于 simple，但只执行一次，systemd 会等它执行完，才启动其他服务。```dbus```：类似于 simple，但会等待 D-Bus 信号后启动。```notify```：类似于 simple，启动结束后会发出通知信号，然后 systemd 再启动其他服务。```idle```：类似于 simple，但是要等到其他任务都执行完，才会启动该服务。一种使用场合是为让该服务的输出，不与其他服务的输出相混合。
EnvironmentFile　　　 | 可以指定启动脚本的环境配置文件！例如 sshd.service 的配置文件写入到 /etc/sysconfig/sshd 当中！你也可以使用 Environment=后面接多个不同的 Shell 变量来给予设置！
ExecStart | 就是实际执行此 daemon 的指令或脚本程序。你也可以使用 ExecStartPre（之前）以及 ExecStartPost（之后）两个设置项目来在实际启动服务前，进行额外的指令行为。但是你得要特别注意的是，指令串仅接受“指令 参数 参数...”的格式，不能接受 <,>,>>,&等特殊字符，很多的 bash 语法也不支持喔！所以，要使用这些特殊的字符时，最好直接写入到指令脚本里面去！不过，上述的语法也不是完全不能用，亦即，若要支持比较完整的 bash 语法，那你得要使用 Type=oneshot 才行喔！其他的 Type 才不能支持这些字符。
ExecStop | 与```systemctl stop```的执行有关，关闭此服务时所进行的指令。
ExecReload | 与```systemctl reload```有关的指令行为。
Restart | 当设置 Restart=1 时，则当此 daemon 服务终止后，会再次的启动此服务。
RemainAfterExit | 当设置为 RemainAfterExit=1 时，则当这个 daemon 所属的所有程序都终止之后，此服务会再尝试启动。这对于 Type=oneshot 的服务很有帮助！
TimeoutSec | 若这个服务在启动或者是关闭时，因为某些缘故导致无法顺利“正常启动或正常结束”的情况下，则我们要等多久才进入“强制结束”的状态！
KillMode | 可以是```process```,```control-group```,```none```的其中一种，如果是```process```则 daemon 终止时，只会终止主要的程序（ExecStart 接的后面那串指令），如果是```control-group```时，则由此 daemon 所产生的其他 control-group 的程序，也都会被关闭。如果是```none```的话，则没有程序会被关闭。
RestartSec | 与 Restart 有点相关性，如果这个服务被关闭，然后需要重新启动时，大概要 sleep 多少时间再重新启动的意思。默认是 100ms（毫秒）。

Install 字段 | 参数意义说明
----|---
WantedBy　　　　　　|  这个设置后面接的大部分是*.target unit！意思是，这个 unit 本身是附挂在哪一个 target unit 下面的！一般来说，大多的服务性质的 unit 都是附挂在 multi-user.target 下面！
Also | 当目前这个 unit 本身被 enable 时，Also 后面接的 unit 也请 enable 的意思！也就是具有相依性的服务可以写在这里呢！
Alias | 进行一个链接的别名的意思！当 systemctl enable 相关的服务时，则此服务会进行链接文件的创建/usr/lib/systemd/system/multi-user.target。

#### 配置 unit 开机启动

开机时，systemd 默认从目录/etc/systemd/system/读取配置文件。但是，里面存放的大部分文件都是符号链接，指向目录/usr/lib/systemd/system/，真正的配置文件存放在那个目录。```systemctl enable```命令用于在上面两个目录之间，建立符号链接关系，相当于激活开机启动。与之对应的，```systemctl disable```命令用于在两个目录之间，撤销符号链接关系，相当于撤销开机启动。

#### 启动和停止 unit

执行```systemctl start```命令启动软件，执行```systemctl status```命令查看该服务的状态

<img src="./Centos7 下使用 systemd 管理服务/systemctl_status.png">

上面的输出结果含义如下：
>Loaded 行：配置文件的位置，是否设为开机启动
Drop-In 行：符号链接地址
Active 行：表示正在运行
Main PID 行：主进程 ID
CGroup 块：应用的所有子进程

当不需要服务继续运行时，可以执行```systemctl stop```命令终止正在运行的服务。有时候，该命令可能没有响应，服务停不下来，这时候可以执行```systemctl kill```命令强制终止。另外，需要重启服务时可以执行```systemctl restart```命令。

### 二、Target

启动计算机的时候，需要启动大量的 unit。如果每一次启动，都要一一写明本次启动需要哪些 unit，显然非常不方便。Systemd 的解决方案就是 target。

简单说，target 就是一个 unit 组，包含许多相关的 unit 。启动某个 target 的时候，systemd 就会启动里面所有的 unit。从这个意义上说，target 这个概念类似于"状态点"，启动某个 target 就好比启动到某种状态。

传统的 init 启动模式里面，有 runlevel 的概念，跟 target 的作用很类似。不同的是，runlevel 是互斥的，不可能多个 runlevel 同时启动，但是多个 target 可以同时启动。

#### 查看 target

我们可以执行指令```systemctl list-unit-files --type=target```查看当前系统的所有 target。也可以执行指令```systemctl list-dependencies multi-user.target```查看一个 target 包含的所有 unit。

系统启动时 systemctl 会根据/etc/systemd/system/default.target 规划的策略进行启动，我们可以通过执行指令```systemctl get-default```查看启动时默认的 target（一般是 multi-user.target）。指令```systemctl set-default```可以设置启动时的默认 target。切换 target 时，默认不关闭前一个 target 启动的进程，我们可以通过```systemctl isolate```关闭前一个 target 里面所有不属于后一个 target 的进程。

### 三、日志管理

Systemd 统一管理所有 unit 的启动日志。带来的好处就是，可以只用```journalctl```一个命令，查看所有日志（内核日志和应用日志）。日志的配置文件是/etc/systemd/journald.conf。

#### 查看日志
我们可以通过指令```journalctl```查看所有日志（默认情况下 ，只保存本次启动的日志）。```journalctl -k```可以查看内核日志，```journalctl -b```和```journalctl -b -0```可以查看系统本次启动的日志，```journalctl -b -1```可以查看上一次启动的日志，```journalctl _PID=X```查看指定进程的日志，```journalctl /usr/bin/bash```查看某个路径的脚本的日志，```journalctl -u redis.service```和```journalctl -u redis.service --since today```查看某个 unit 的日志。

## Systemd 的特性（对比 SysVInit）

为了保证运行在先前 Linux 版本上的应用程序运行稳定，systemd 兼容了原先的 SysVInit 以及 LSB initscripts，但也引入了新的特性。这使得系统中已经存在的服务和进程无需修改，降低了系统向 systemd 迁移的成本。但我们也应该了解 systemd 所做的改变，以更好的适应当前的版本。大体而言，systemd 相比 SysVInit 更改了以下几个方面：

### 一、支持并行启动

系统启动时，需要启动很多启动项目，在 SysVInit 中，每一个启动项目都由一个独立的脚本负责，它们由 SysVinit 顺序地，串行地调用。因此总的启动时间是各脚本运行时间之和。而 systemd 通过 socket/D-Bus activation 等技术，能够将启动项目同时并行启动，大大提高了系统的启动速度。

### 二、提供按需启动能力

当 sysvinit 系统初始化的时候，它会将所有可能用到的后台服务进程全部启动运行。并且系统必须等待所有的服务都启动就绪之后，才允许用户登录。这种做法有两个缺点：首先是启动时间过长；其次是系统资源浪费。

某些服务很可能在很长一段时间内，甚至整个服务器运行期间都没有被使用过。比如 CUPS，打印服务在多数服务器上很少被真正使用到。您可能没有想到，在很多服务器上 SSHD 也是很少被真正访问到的。花费在启动这些服务上的时间是不必要的；同样，花费在这些服务上的系统资源也是一种浪费。

Systemd 可以提供按需启动的能力，只有在某个服务被真正请求的时候才启动它。当该服务结束，systemd 可以关闭它，等待下次需要时再次启动它。

### 三、采用 Linux 的 Cgroup 特性跟踪和管理进程的生命周期

Init 系统的一个重要职责就是负责跟踪和管理服务进程的生命周期。它不仅可以启动一个服务，也必须也能够停止服务。这看上去没有什么特别的，然而在真正用代码实现的时候，我们会发现有时候停止服务比一开始想的要困难。

服务进程一般都会作为守护进程（daemon）在后台运行，为此服务程序有时候会派生 (fork) 两次。在 SysVInit 中，需要在配置文件中正确地配置 expect 小节。这样 SysVInit 通过对 fork 系统调用进行计数，从而获知真正的守护进程的 PID 号。

还有更加特殊的情况。比如，一个 CGI 程序会派生两次，从而脱离了和 Apache 的父子关系。当 Apache 进程被停止后，该 CGI 程序还在继续运行。而我们希望服务停止后，所有由它所启动的相关进程也被停止。

为了处理这类问题，SysVInit 通过 strace 来跟踪 fork、exit 等系统调用，但是这种方法很笨拙，且缺乏可扩展性。Systemd 则利用了 Linux 内核的特性即 CGroup 来完成跟踪的任务。当停止服务时，通过查询 CGroup，Systemd 可以确保找到所有的相关进程，从而干净地停止服务。

CGroup 已经出现了很久，它主要用来实现系统资源配额管理。CGroup 提供了类似文件系统的接口，使用方便。当进程创建子进程时，子进程会继承父进程的 CGroup。因此无论服务如何启动新的子进程，所有的这些相关进程都会属于同一个 CGroup，systemd 只需要简单地遍历指定的 CGroup 即可正确地找到所有的相关进程，将它们一一停止即可。

### 四、启动挂载点和自动挂载的管理

传统的 Linux 系统中，用户可以用/etc/fstab 文件来维护固定的文件系统挂载点。这些挂载点在系统启动过程中被自动挂载，一旦启动过程结束，这些挂载点就会确保存在。这些挂载点都是对系统运行至关重要的文件系统，比如 HOME 目录。和 SysVInit 一样，Systemd 会管理这些挂载点，以便能够在系统启动时自动挂载它们。Systemd 兼容了/etc/fstab 文件，我们可以继续使用该文件管理挂载点。

有时候用户还需要动态挂载点，比如打算访问 DVD 内容时，才临时执行挂载以便访问其中的内容，而不访问光盘时该挂载点被取消 (umount)，以便节约资源。传统地，人们依赖 autofs 服务来实现这种功能。

Systemd 内建了自动挂载服务，无需另外安装 autofs 服务，可以直接使用 systemd 提供的自动挂载管理能力来实现 autofs 的功能。

### 五、实现事务性依赖关系管理

系统启动过程是由很多的独立工作共同组成的，这些工作之间可能存在依赖关系，比如挂载一个 NFS 文件系统必须依赖网络能够正常工作。Systemd 虽然能够最大限度地并发执行很多有依赖关系的工作，但是类似"挂载 NFS"和"启动网络"这样的工作还是存在天生的先后依赖关系，无法并发执行。对于这些任务，systemd 维护一个"事务一致性"的概念，保证所有相关的服务都可以正常启动而不会出现互相依赖，以至于死锁的情况。

### 六、能够对系统进行快照和恢复

Systemd 支持按需启动，因此系统的运行状态是动态变化的，人们无法准确地知道系统当前运行了哪些服务。Systemd 快照提供了一种将当前系统运行状态保存并恢复的能力。

比如系统当前正运行服务 A 和 B，可以用 systemd 命令行对当前系统运行状况创建快照。然后将进程 A 停止，或者做其他的任意的对系统的改变，比如启动新的进程 C。在这些改变之后，运行 systemd 的快照恢复命令，就可立即将系统恢复到快照时刻的状态，即只有服务 A，B 在运行。一个可能的应用场景是调试：比如服务器出现一些异常，为了调试用户将当前状态保存为快照，然后可以进行任意的操作，比如停止服务等等。等调试结束，恢复快照即可。

这个快照功能目前在 systemd 中并不完善，似乎开发人员也没有特别关注它，因此有报告指出它还存在一些使用上的问题，使用时尚需慎重。

### 七、日志服务

systemd 自带日志服务 journald，该日志服务的设计初衷是克服现有的 syslog 服务的缺点。比如：
- syslog 不安全，消息的内容无法验证。每一个本地进程都可以声称自己是 Apache PID 4711，而 syslog 也就相信并保存到磁盘上。
- 数据没有严格的格式，非常随意。自动化的日志分析器需要分析人类语言字符串来识别消息。一方面此类分析困难低效；此外日志格式的变化会导致分析代码需要更新甚至重写。

Systemd Journal 用二进制格式保存所有日志信息，用户使用 journalctl 命令来查看日志信息。无需自己编写复杂脆弱的字符串分析处理程序。

Systemd Journal 的优点如下：

- 简单性：代码少，依赖少，抽象开销最小。
- 零维护：日志是除错和监控系统的核心功能，因此它自己不能再产生问题。举例说，自动管理磁盘空间，避免由于日志的不断产生而将磁盘空间耗尽。
- 移植性：日志文件应该在所有类型的 Linux 系统上可用，无论它使用的何种 CPU 或者字节序。
- 性能：添加和浏览日志非常快。
- 最小资源占用：日志数据文件需要较小。
- 统一化：各种不同的日志存储技术应该统一起来，将所有的可记录事件保存在同一个数据存储中。所以日志内容的全局上下文都会被保存并且可供日后查询。例如一条固件记录后通常会跟随一条内核记录，最终还会有一条用户态记录。重要的是当保存到硬盘上时这三者之间的关系不会丢失。Syslog 将不同的信息保存到不同的文件中，分析的时候很难确定哪些条目是相关的。
- 扩展性：日志的适用范围很广，从嵌入式设备到超级计算机集群都可以满足需求。
- 安全性：日志文件是可以验证的，让无法检测的修改不再可能。

## 总结

Systemd 作为 Centos7 最新采用的系统管理进程，相比前任有相当多的改变。它的优点是功能强大，使用方便，缺点是过于复杂，与操作系统的其他部分强耦合，可能在某种程度上违背了 Linux 原本"keep simple, keep stupid"设计哲学。但从一个系统使用者的角度，它的确在很多方面做得都要比它的前任更好。作为一个后端，我们需要对这些改变有所了解，才能将这个系统用得更好。

## 参考资料

1、[鸟哥的 Linux 私房菜：基础学习篇 第四版 第十九章 ](https://wizardforcel.gitbooks.io/vbird-linux-basic-4e/content/165.html)
2、[Systemd 入门教程 - 阮一峰的网络日志 ](http://www.ruanyifeng.com/blog/2016/03/systemd-tutorial-commands.html)
3、[CentOS / RHEL 7 : How to set default target (default runlevel)](https://www.thegeekdiary.com/rhel-centos-7-how-to-set-default-target-replaced-runlevel/)
4、[IBM developerWorks Systemed](https://www.ibm.com/developerworks/cn/linux/1407_liuming_init3/index.html)