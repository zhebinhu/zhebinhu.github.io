---
title: Spring 源码浅析——容器刷新流程概览
tags: 
	- Spring
toc: true
date: 2019-03-03 17:08:49
---
<!--more-->
本文是 Spring 源码浅析系列的第一篇。Spring 版本是 Spring Boot 2.1.2.RELEASE （即 Spring 5.1.4），以默认配置启动，分析框架工作的原理。

众所周知，Spring 以容器管理所有的 bean 对象，容器的实体是一个 BeanFactory 对象。但我们常用的容器是另一个 ApplicationContext ，它在内部持有了 BeanFactory，所有和 BeanFactory 相关的操作都会委托给内部的 BeanFactory 来完成。

ApplicationContext 的继承关系如下图所示：

<center><img src="./Spring 源码浅析——容器创建流程概览/ApplicationContext 继承关系.png" width="70%" length="70%"/></center>


ApplicationContext 是一个接口，**ClassPathXmlApplicationContext**和**AnnotationConfigApplicationContext**是两个比较常用的实现类，前者基于 xml 使用，后者基于注解使用。SpringBoot 中默认后面一种。

ApplicationContext 也继承了 BeanFactory 接口，BeanFactory 的继承关系如下图所示：

<center><img src="./Spring 源码浅析——容器创建流程概览/BeanFactory 继承关系.png" width="70%" length="70%"/></center>

从继承关系我们可以获得以下信息：
- ApplicationContext 继承了 ListableBeanFactory，这个 Listable 的意思就是，通过这个接口，我们可以获取多个 Bean，最顶层 BeanFactory 接口的方法都是获取单个 Bean 的。
- ApplicationContext 继承了 HierarchicalBeanFactory，Hierarchical 的意思是说我们可以在应用中起多个 BeanFactory，然后可以将各个 BeanFactory 设置为父子关系。

ApplicationContext 非常重要，所以我们第一篇就看一下 ApplicationContext 初始化的过程。默认配置下，SpringBoot 中的 ApplicationContext 初始化在 refresh() 方法中，为什么叫 refresh() 而不是 init() 呢？因为 ApplicationContext 建立起来以后，其实我们是可以通过调用 refresh() 这个方法重建的，这样会将原来的 ApplicationContext 销毁，然后再重新执行一次初始化操作。

## 1、容器刷新概览
`refresh` 是个总览全局的方法，我们可以通过这个方法概览容器刷新的过程：
// AbstractApplicationContext 511
```java
@Override
public void refresh() throws BeansException, IllegalStateException {
    synchronized (this.startupShutdownMonitor) {
        // 准备工作，记录下容器的启动时间、标记“已启动”状态、检验配置文件格式
        prepareRefresh();
        // 获取 Spring 容器
        ConfigurableListableBeanFactory beanFactory = obtainFreshBeanFactory();
        // 设置 BeanFactory 的类加载器，添加几个 BeanPostProcessor，手动注册几个特殊的 bean 等
        prepareBeanFactory(beanFactory);
        try {
            // BeanFactory 准备工作完成后进行的后置处理工作，子类可以自定义实现，Spring Boot 中是个空方法
            postProcessBeanFactory(beanFactory);
            //=======以上是 BeanFactory 的预准备工作=======
            // 调用 BeanFactoryPostProcessor 各个实现类的 postProcessBeanFactory(factory) 方法
            // SpringBoot 会在这里扫描 @Component 注解和进行自动配置
            invokeBeanFactoryPostProcessors(beanFactory);
            // 注册和创建 BeanPostProcessor 的实现类（注意和之前的 BeanFactoryPostProcessor 的区别）
            registerBeanPostProcessors(beanFactory);
            // 初始化 MessageSource 组件（做国际化功能；消息绑定，消息解析）
            initMessageSource();
            // 初始化当前 ApplicationContext 的事件广播器
            initApplicationEventMulticaster();
            // 具体的子类可以在这里初始化一些特殊的 Bean（在初始化 singleton beans 之前），Spring Boot 中默认没有定义
            onRefresh();
            // 注册事件监听器，监听器需要实现 ApplicationListener 接口
            registerListeners();
            // 初始化所有的 singleton beans（lazy-init 的除外）
            finishBeanFactoryInitialization(beanFactory);
            // 容器刷新完成操作
            finishRefresh();
        }
        catch (BeansException ex) {
            if (logger.isWarnEnabled()) {
                logger.warn("Exception encountered during context initialization - " +
                        "cancelling refresh attempt: " + ex);
            }
            destroyBeans();
            cancelRefresh(ex);
            throw ex;
        }
        finally {
            resetCommonCaches();
        }
    }
}
```

通过上面的代码和注释我们总览了容器刷新的整个流程，下面我们来一步步探索每个环节都做了什么。

## 2、刷新前的准备工作

这步比较简单，直接看代码中的注释即可。
// AbstractApplicationContext 580
```java
protected void prepareRefresh() {
    // 记录启动时间，
    // 将 active 属性设置为 true，closed 属性设置为 false，它们都是 AtomicBoolean 类型
    this.startupDate = System.currentTimeMillis();
    this.closed.set(false);
    this.active.set(true);

    // Spring Boot 中是个空方法
    initPropertySources();

    // 校验配置属性的合法性
    getEnvironment().validateRequiredProperties();

    // 记录早期的事件
    this.earlyApplicationEvents = new LinkedHashSet<>();
}
```

## 3、获取 Bean 容器

前面说过 ApplicationContext 内部持有了一个 BeanFactory，这步就是获取 ApplicationContext 中的 BeanFactory。在 ClassPathXmlApplicationContext 中会做很多工作，因为一开始 ClassPathXmlApplicationContext 中的 BeanFactory 并没有创建，但在 AnnotationConfigApplicationContext 比较简单，直接返回即可。
// AbstractApplicationContext 621
```java
protected ConfigurableListableBeanFactory obtainFreshBeanFactory() {
    // 通过 cas 设置刷新状态
    if (!this.refreshed.compareAndSet(false, true)) {
        throw new IllegalStateException(
                "GenericApplicationContext does not support multiple refresh attempts: just call 'refresh' once");
    }
    // 设置序列号
    this.beanFactory.setSerializationId(getId());
    // 返回已创建的 BeanFactory
    return this.beanFactory;
}
```
## 4、准备 Bean 容器

BeanFactory 获取之后并不能马上使用，还要在 BeanFactory 中做一些准备工作，包括类加载器、表达式解析器的设置，几个特殊的 BeanPostProcessor 的添加等。
// AbstractApplicationContext 631
```java
    protected void prepareBeanFactory(ConfigurableListableBeanFactory beanFactory) {
        // 设置 BeanFactory 的类加载器，这里设置为当前 ApplicationContext 的类加载器
        beanFactory.setBeanClassLoader(getClassLoader());
        // 设置表达式解析器
        beanFactory.setBeanExpressionResolver(new StandardBeanExpressionResolver(beanFactory.getBeanClassLoader()));
        beanFactory.addPropertyEditorRegistrar(new ResourceEditorRegistrar(this, getEnvironment()));
        
        // 添加Aware后置处理器，实现了 Aware 接口的 beans 在初始化的时候，这个 processor 负责回调
        beanFactory.addBeanPostProcessor(new ApplicationContextAwareProcessor(this));
        
        /**
         * 下面几行的意思是，如果某个 bean 依赖于以下几个接口的实现类，在自动装配的时候忽略它们，Spring 会通过其他方式来处理这些依赖
         */
        beanFactory.ignoreDependencyInterface(EnvironmentAware.class);
        beanFactory.ignoreDependencyInterface(EmbeddedValueResolverAware.class);
        beanFactory.ignoreDependencyInterface(ResourceLoaderAware.class);
        beanFactory.ignoreDependencyInterface(ApplicationEventPublisherAware.class);
        beanFactory.ignoreDependencyInterface(MessageSourceAware.class);
        beanFactory.ignoreDependencyInterface(ApplicationContextAware.class);

        /**
        * 下面几行是为了解决特殊的依赖，如果有 bean 依赖了以下几个（可以发现都是跟容器相关的接口），会注入这边相应的值，
        * 这是因为 Spring 容器里面不保存容器本身，所以容器相关的依赖要到 resolvableDependencies 里面找。上文有提到过，
        * ApplicationContext 继承了 ResourceLoader、ApplicationEventPublisher、MessageSource，所以对于这几个依赖，
        * 可以赋值为 this，注意 this 是一个 ApplicationContext。
        * 那这里怎么没看到为 MessageSource 赋值呢？那是因为 MessageSource 被注册成为了一个普通的 bean
        */
        beanFactory.registerResolvableDependency(BeanFactory.class, beanFactory);
        beanFactory.registerResolvableDependency(ResourceLoader.class, this);
        beanFactory.registerResolvableDependency(ApplicationEventPublisher.class, this);
        beanFactory.registerResolvableDependency(ApplicationContext.class, this);


        /**
         * 这也是个 BeanPostProcessor ，在 bean 实例化后，如果是 ApplicationListener 的子类，那么将其添加到 listener 列表中，
         * 可以理解成：注册监听器
         */
        beanFactory.addBeanPostProcessor(new ApplicationListenerDetector(this));
        
        if (beanFactory.containsBean(LOAD_TIME_WEAVER_BEAN_NAME)) {
            beanFactory.addBeanPostProcessor(new LoadTimeWeaverAwareProcessor(beanFactory));
            beanFactory.setTempClassLoader(new ContextTypeMatchClassLoader(beanFactory.getBeanClassLoader()));
        }


        /**
         * 从下面几行代码我们可以知道，Spring 往往很 "智能" 就是因为它会帮我们默认注册一些有用的 bean，我们也可以选择覆盖
         */
        if (!beanFactory.containsLocalBean(ENVIRONMENT_BEAN_NAME)) {
            beanFactory.registerSingleton(ENVIRONMENT_BEAN_NAME, getEnvironment());
        }
        if (!beanFactory.containsLocalBean(SYSTEM_PROPERTIES_BEAN_NAME)) {
            beanFactory.registerSingleton(SYSTEM_PROPERTIES_BEAN_NAME, getEnvironment().getSystemProperties());
        }
        if (!beanFactory.containsLocalBean(SYSTEM_ENVIRONMENT_BEAN_NAME)) {
            beanFactory.registerSingleton(SYSTEM_ENVIRONMENT_BEAN_NAME, getEnvironment().getSystemEnvironment());
        }
    }
```

## 5、调用 BeanFactory 后置处理器

调用 BeanDefinitionRegistryPostProcessor 的 `postProcessBeanDefinitionRegistry(registry)` 方法和 BeanFactoryPostProcessor 的 `postProcessBeanFactory(beanFactory)` 方法，它允许在 beanFactory 准备完成之后对 beanFactory 进行一些修改，比如在 bean 初始化之前对 beanFactory 中的 beanDefinition 进行修改。@ComponentScan 和 @EnableAutoConfiguration 这两个注解都是在这里实现的。

这里有个非常重要的后置处理器：ConfigurationClassPostProcessor，它的作用是在这里解析 @Configuration 标签。@PropertySource、@ComponentScan、@Import、@ImportResource、@Bean 这些注解都和 @Configuration 相关，都会在这里被解析。我们常用的 @Component 注解和 SpringBoot 的自动配置，都是在这里被实现。ConfigurationClassPostProcessor 会以我们在 Spring 启动时传入的启动类作为解析 @Configuration 的根节点（SpringApplication.run(**SpringTest.class**,args);），递归地扫描其它 @Configuration 节点，最终把所有用户自定义的 bean 以 Map&lt;beanName,beanDefinition&gt; 的形式保存在容器中。

相关博客：[Spring源码解析 – @Configuration配置类及注解Bean的解析](https://www.cnblogs.com/ashleyboy/p/9667485.html)

## 6、注册各类 Bean 后置处理器

也是一个名字就体现功能的方法，把各种 BeanPostProcessor 注册到 BeanFactory 中（需要注意的是这里的注册会直接调用 getBean 创建对象），BeanPostProcessor 允许在 bean 初始化前后插手对 bean 的初始化过程，不展开了。

## 7、初始化事件分派器

Event 会有单独的篇幅详解，这里就不展开了。

## 8、初始化所有非懒加载 singleton beans

这是容器刷新中最重要的方法。Spring 需要在这个阶段完成所有的 singleton beans 的实例化。这一步骤非常重要而且过程非常长，下一篇中我们来专门分析这个方法。

## 9、容器刷新完成
// AbstractApplicationContext 871
```java
    protected void finishRefresh() {
        clearResourceCaches();

        // 创建Lifecycle处理器
        initLifecycleProcessor();

        // 调用LifecycleProcessor的onRefresh()方法，默认是调用所有Lifecycle的start()方法
        getLifecycleProcessor().onRefresh();

        // 发布容器刷新完成事件
        publishEvent(new ContextRefreshedEvent(this));
        
        LiveBeansView.registerApplicationContext(this);
    }
```

## 总结

本篇文章简单梳理了一遍 Spring IOC 的核心代码 `refresh()` 的部分，着重跟进了容器准备的部分，比如 ApplicationContext 的预准备、BeanFactory 的获取、BeanFactory 的预准备等等。容器准备好了，接下来就要往容器中注入 bean 了，下一篇将分析 Spring 是如何创建并往容器中注入 bean。

## 参考资料
[Spring中bean后置处理器BeanPostProcessor](https://www.jianshu.com/p/f80b77d65d39)
[Spring IOC 容器源码分析](https://javadoop.com/post/spring-ioc)
[Spring IOC 容器源码分析系列文章导读](http://www.tianxiaobo.com/2018/05/30/Spring-IOC-%E5%AE%B9%E5%99%A8%E6%BA%90%E7%A0%81%E5%88%86%E6%9E%90%E7%B3%BB%E5%88%97%E6%96%87%E7%AB%A0%E5%AF%BC%E8%AF%BB/#47-beanpostprocessor)