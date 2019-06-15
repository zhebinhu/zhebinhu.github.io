---

title: GET 与 POST 的区别
tags: 计算机网络
toc: true
date: 2018-05-15 14:55:30
---
<!--more-->
HTTP 定义了一组请求方法, 以表明要对给定资源执行的操作。而硕果仅存的只剩两个半（笑）。实际开发中我们常用到的一般是 POST 和 GET，极少数情况下会用到 PUT。[RFC7231](https://tools.ietf.org/html/rfc7231#section-4) 规范了 GET 方法用于请求一个指定资源的表示形式（transfer a current representation of the target resource），而 POST 方法用于将实体提交到指定的资源（Perform resource-specific processing on the request payload）。但仅仅了解规范是不够的，很多工具比如 chrome,nginx 有它自己履行规范的方式，从开发角度看，或许这些更有价值。

## 参数
GET 传递的参数只能带 URL 后面，文本格式 QueryString，长度受限于浏览器发送长度和服务器接收长度。各家标准不一，作为开发人员宜选取其中最短一个（2083 字节）作为开发标准，以避免不必要的兼容问题。
- IE(Browser)　2,083 Bytes
- Firefox(Browser)　65,536 Bytes
- Safari(Browser)　80,000 Bytes
- Opera(Browser)　190,000 Bytes
- Google (chrome)　8,182 Bytes
- Apache (Server)　8,182 Bytes
- Microsoft Internet Information Server(IIS)　16,384 Bytes

POST 的参数就比较灵活，可以传递 application/x-www-form-urlencoded 的类似 QueryString、multipart/form-data 的二进制报文格式（支持文件信息嵌入报文传输）、纯文本或二进制的 body 参数。很多时候我们把参数写在 body 里，这时参数没有长度上的限制。

## 幂等
幂等是一个计算机术语，表示重复执行某一操作得到的结果总是相同的。在 HTTP 中，如果我们说一个 HTTP 方法是幂等的，指的是同样的请求被执行一次与连续执行多次的效果是一样的，服务器的状态也是一样的。

GET 是幂等的，我们使用 GET 获取服务器上同一份数据，拿到的数据应该都是相同的。每次请求后服务器的状态应该也是相同的（统计数据除外）。

POST 不是幂等的，多次 POST 返回的结果不一定相同，每次请求后服务器的状态也是不一样的。

## 缓存
GET 时默认可以复用前面的请求数据作为缓存结果返回，此时以完整的 URL 作为缓存数据的 KEY。所以有时候为了强制每次请求都是新数据，我们可以在 URL 后面加上一个随机参数或时间戳或版本号来避免从缓存中读取，也可以直接设置 Cache-Control 禁用缓存。

POST 则一般不会被这些缓存因素影响。

## 安全性

服务器的日志比如像 nginx 的 access log 会自动记录 GET 和 POST 的 URL，包括其中带的参数，但不会记录请求的报文。对于一些敏感数据，POST 更安全一些。

## 自动化性能测试
基于上面提到的 nginx 日志，可以使用 grep GET+日期，awk 格式化，然后 sort -u 去重，从而提取到某天的所有 GET 请求 URL，使用程序模拟登陆，然后请求所有 URL 即可获取简单的性能测试数据，每个请求是否正确，响应时间多少等等。

但是对于 POST 请求，因为不知道报文，无法这样简单处理。可以通过 nginx-lua 获取报文输出到 log，这样格式化会麻烦很多，但不失为一个办法。

## TCP 包的数量

GET 请求稳定只发送一个包，而 POST 请求在某些浏览器里会发送两个，具体的原因还在探究。
- IE 6 – 2 packets
- IE 7 – 2 packets
- IE 8 – 2 packets
- Firefox 3.0.13 – 1 packet
- Firefox 3.5.2 – 1 packet
- Opera 9.27 – 2 packets
- Safari 4.0.3 – 2 packets
- Chrome 2.0.172.43 – 2 packets

## 参考资料
1、[URL 最大长度问题 ](https://www.cnblogs.com/henryhappier/archive/2010/10/09/1846554.html)
2、[xmlhttprequest-xhr-uses-multiple-packets-for-http-post](https://blog.josephscott.org/2009/08/27/xmlhttprequest-xhr-uses-multiple-packets-for-http-post/)
3、[comparing-get-and-post](http://kimmking.github.io/2017/12/01/comparing-get-and-post/)