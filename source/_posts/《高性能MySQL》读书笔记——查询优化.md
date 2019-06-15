---
title: 《高性能 MySQL》读书笔记——查询优化
tags: MySQL
toc: true
date: 2018-08-28 18:34:21
---
<!--more-->
在设计了最优的库表结构、如何建立最好的索引，这些对于高性能来说必不可少。但这些还不够，还需要合理地设计查询。

## 一、查询执行的基础
当 MySQL 执行一个查询语句时，会经历以下几个步骤：

<img src="./《高性能 MySQL》读书笔记——查询优化/查询执行基础.png"/>

- 客户端发送一条查询给服务器。
- 服务器先检查查询缓存，如果命中了缓存，则立刻返回存储在缓存中的结果。否则进入下一阶段。
- 服务器端进行 SQL 解析、预处理，再由优化器生成对应的执行计划。
- MySQL 根据优化器生成的执行计划，调用存储引擎的 API 来执行查询。
- 将结果返回给客户端。

## 二、MySQL 查询优化器

MySQL 查询优化器会做大量的工作，这些工作包括但不限于：

### 1. 重新定义关联表的顺序

MySQL 使用一种叫 “嵌套循环关联” 的方式来执行关联查询。顾名思义，这是一种嵌套式的查询。在正常情况下，最左边的表会嵌套在最外层，然后根据表中的每一行数据去遍历内层表，找到所有符合条件的行。如果外层表行数为 m，内层表行数为 n，则总共要遍历 m*n 行数据。

但如果内层表使用了索引，而关联字段恰好就被索引覆盖的话，就只需要几次查询就可以定位内层表的数据行。总行数从 m\*n 变为 m\*i(i 一般小于 3)。这无疑大大加快了关联查询的速度。MySQL 查询优化器会调整关联表查询的顺序来尽可能使用多的索引查询。

### 2. 将外连接转化成内连接
并不是所有的 OUTER JOIN 语句都必须以外连接的方式执行。诸多原因，例如 WHERE 条件、库表结构都可能让一个外连接等价于一个内连接。MySQL 能够识别这点并重写查询，让其可以调整关联顺序（外连接分左右，所以无法调整顺序）。

### 3. 使用等价变换规则
MySQL 可以合并和减少一些比较，例如（5=5 AND a>5）将被改写成（a>5）。

### 4. 优化 COUNT()、MIN() 和 MAX()
索引和是否可为空可以帮助 MySQL 优化这类表达式。例如要找某一列的最小值，只需查询对应 B-tree 索引最左端的记录，而最大值只需查询对应 B-tree 索引最右端。另外，没有任何 WHERE 条件的 COUNT(\*) 查询在 MyISAM 中也是 O(1)，因为 MyISAM 维护了一个变量来存放数据表的行数（不过 innodb 没有，innodb 中执行 COUNT(\*) 会做全表查询）。

### 5. 预估并转化为常数表达式
当 MySQL 检测到一个表达式或者一个子查询可以转化为常数的时候，就会一直把该表达式作为常数进行优化处理。

### 6. 覆盖索引扫描
当索引中的列覆盖所有查询中需要使用的列时，MySQL 将直接使用索引返回所需数据而不做回表查询。

### 7. 提前终止查询
在发现已经满足查询要求的时候，MySQL 总是能够立刻终止查询。比如 LIMIT。

### 8. 子查询优化
MySQL 5.6 中处理子查询的思路是，基于查询重写技术的规则，尽可能将子查询转换为连接，并配合基于代价估算的 Materialize、exists 等优化策略让子查询执行更优。

### 9. 等值传播
如果两个列的值通过等式关联，那么 MySQL 能够把其中一个列的 WHERE 语句条件传递到另一列上。例如：
> SELECT film.film_id FROM film INNER JOIN film_actor USING(film_id) WHERE film.film_id > 500;

优化器会把它优化为：
> SELECT film.film_id FROM film INNER JOIN film_actor USING(film_id) WHERE film.film_id > 500 AND film_actor.film_id > 500;

### 10. 列表 IN() 的比较
MySQL 会将 IN() 列表中的数据先进行排序，然后通过二分查找的形式来确定取出的值是否在列表中。

### 11. 索引合并
当 WHERE 子句中包含多个复杂条件涉及到多个索引时，MySQL 会先根据不同索引取出多组数据，再将这些数据合并。

## 三、MySQL 查询优化器的局限
### 1. 关联子查询
上一节有提到 MySQL 查询优化器会把 IN 子查询变为 EXISTS 子查询的形式，大部分情况下这种优化会带来性能提升，但某些情况下，会让查询更慢。比如：
> SELECT * FROM film WHERE film_id IN(SELECT film_id FROM film_actor WHERE actor_id = 1);

假设 film 和 film_actor 表在 film_id 上都有索引，那么这条语句会走 film_actor 和 film 的索引，速度非常快。但查询优化器会把它 “优化” 为：
> SELECT * FROM film WHERE EXISTS(SELECT 1 FROM film_actor WHERE actor_id = 1 AND film.film_id = actor.film_id);

此时 MySQL 只会走 film_actor 的索引而会对 film 做全表扫描，效率大大下降。

解决的方法就是使用左外连接改造：
> SELECT film.* FROM film LEFT OUTER JOIN film_actor USING(film_id) WHERE film_actor.actor_id = 1;


**PS：5.6 及以后版本的 MySQL 对关联子查询做了大量优化，现在的思路是，基于查询重写技术的规则，尽可能将子查询转换为连接，并配合基于代价估算的 Materialize、exists 等优化策略让子查询执行更优。因此 5.6 以后将不存在这个问题。**

### 2.UNION 的限制
MySQL 无法将限制条件从外层 “下推” 到内层，其中一个典型就是 UNION：
> (SELECT first_name FROM actor) UNION ALL (SELECT first_name FROM customer) LIMIT 20;

MySQL 会把 actor 和 customer 中的所有记录放在同一张临时表中，然后从临时表中取出前 20 条。可以通过把 LIMIT 放入内部来解决这个问题：
> (SELECT first_name FROM actor LIMIT 20) UNION ALL (SELECT first_name FROM customer LIMIT 20) LIMIT 20;

这样临时表的规模就缩小到 40 了。

### 3. 最大值和最小值优化
MySQL 优化器会对不加条件的 MAX 和 MIN 做优化，但并没有对加条件的这两个函数做优化。比如：
> SELECT MIN(actor_id) FROM actor WHERE first_name = "PENELOPE";

actor_id 是主键，严格按照大小排序，那么其实在找到第一个满足条件的记录就可以返回了。而 MySQL 会继续遍历整张表。修改的方式是使用 LIMIT：
> SELECT actor_id FROM actor WHERE first_name = "PENELOPE" LIMIT 1;

此时会触发提前终止机制，返回最小的 actor_id。

## 四、优化特定类型的查询
### 1. 优化 COUNT() 查询

很多时候一些业务场景并不要求完全精确的 COUNT 值，可以使用
> EXPLAIN SELECT * FROM film;

得到的近似值来代替。

innodb 下，如果表中单行数据量很大，且没有二级索引的话，可以对表上较短的且不为空的字段加索引，再执行 count(*），此时优化器会自动选择走二级索引，由于二级索引是短字段，单页存储的数据行数就多，减少了取页的次数，查询时间也就更短了。

### 2. 优化关联查询

确保 ON 或者 USING 子句中的列上有索引，这样只需要全表扫描第一个表，第二个表可以走索引。

确保任何的 GROUP BY 和 ORDER BY 中的表达式只涉及到一个表中的列，这样 MySQL 才可能使用索引来优化这个过程。

### 3. 优化 LIMIT 分页
LIMIT 分页在系统偏移量非常大的时候效果会很差。比如 LIMIT 1000,20 这样的查询，这时 MySQL 需要查询 10020 条记录然后只返回最后 20 条。

优化此类分页查询的一个最简单的办法就是尽可能利用索引覆盖扫描。考虑下面的查询：
> SELECT film_id, description FROM film ORDER BY title LIMIT 50,5;

这个语句可以被改写成：
> SELECT film.film_id,film,description FROM film INNER JOIN(SELECT film_id FROM film ORDER BY title LIMIT 50,5)AS lim USING(film_id);

这里的 “延迟关联” 操作将大大提升查询效率，它会利用覆盖索引直接定位到分页所需数据所在的位置，而不需要从头遍历。

记录上一次取数据的位置也是一个不错的主意。比如在频繁使用 “下一页” 这个功能的时候，记录下上次取数据最后的位置，然后可以把查询语句写成：
> SELECT film_id, description FROM film WHERE film_id>16030 ORDER BY film_id LIMIT 5;