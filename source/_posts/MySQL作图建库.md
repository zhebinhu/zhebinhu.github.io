---

title: MySQL 作图建库
date: 2018-02-03 11:59:36
tags: MySQL
toc: true
---
<!--more-->
workbench 是 MySQL 自带的数据库可视化工具，相比另一款常用的数据库可视化工具 Navicat 最大的优势就是它是免费的。两者的操作逻辑没有太大区别，不过 workbench 英文的界面对初学者不是太友好。我花了一点时间学习了如何作图，希望能为以后节省时间。

E-R 图是描述数据库关系最常用的方式。优点是直观、详尽。workbench 当然也提供了这种图表的绘制方式，不过在里面叫 EER 图。经过我的一番考证，这个 EER 图就是我们常说的 E-R 图。

## 一、已有数据库，自动生成 EER 图：

①、首先在 mysql workbench 里选中 Database——> reverse engineering

②、然后选择你建立的连接（也就是数据库）

③、接下来一路 next，直到最后选择导出的数据库

④、自动生成的 E-R 图大概长相如图：

<img src="./MySQL 作图建库/ER图1.png"/>

## 二、先画 EER 图，然后自动生成数据库：

①、启动软件过后，注意不需要连接数据库（我第一次就是直接连接数据库了所以找不到设计 ER 模型的地方）

②、点击"+" ,进入模型设计界面

<img src="./MySQL 作图建库/作图第一步.png"/>

③、双击 Add Diagram 进入如下设计界面

④、点击工具栏表格，并在设计区域点击，就会出现一个 table1 并双击它

⑤、最后 执行 “File”->"Export" 按钮，选择 Forward Engineer SQL CREATE Script (ctrl+shift+G). 这样就可以把模型导出为 SQL 脚本文件。现在执行这个 SQL 文件就 OK 了