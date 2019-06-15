---
title: Spring 源码浅析——事件和异步事件
tags: 
	- Java
	- Spring
toc: true
date: 2019-03-13 21:47:24
---
## 1、背景知识
### 1.1 观察者模式

Spring事件体系是观察者模式的典型应用。观察者模式简单来说即所有观察者继承一个包含触发方法的父类并重写该方法，然后注册到被观察者的一个列表中。当被观察者发生变化时通过调用列表中所有已注册观察者的触发方法，使观察者得到通知，从而作进一步处理。关于观察者模式的具体描述网上有很多，这里不再赘述。

### 1.2 Spring 事件体系
Spring事件体系包含三个部件：
- 事件：ApplicationEvent
- 事件监听器：ApplicationListener，对监听到的事件进行处理。
- 事件广播器：ApplicationEventMulticaster，将 publish 的事件广播给所有的监听器。通常情况下无需自行实现，Spring 默认提供了 SimpleApplicationEventMulticaster。

### 1.3 Spring 事件实例
这里我们模拟一个交通信号灯状态改变的事件，而相应的监听者应当根据交通信号灯的状态做出不同的反应：红灯停，黄灯等，绿灯行。首先定义一个 LightEvent 继承 ApplicationEvent 来描述交通信号灯状态改变的事件。其中 lightColor 描述信号灯状态，1：红灯 2：黄灯 3：绿灯。
```java
public class LightEvent extends ApplicationEvent {
 
    private int lightColor;
 
    public LightEvent(int lightColor) {
        this.lightColor = lightColor;
    }
 
    public int getLightColor() {
        return lightColor;
    }
}
```
事件监听器实现 ApplicationListener 接口的 onApplicationEvent 方法，<LightEvent>表明该监听器只关心 LightEvent 事件，不关心其他类型的事件。
```java
@Component
public class LightEventListener implements ApplicationListener<LightEvent>{
 
    @Override
    public void onApplicationEvent(LightEvent lightEvent) {
        switch(lightEvent.getLightColor()){
            case 1:
                System.out.println("红灯停");
                break;
            case 2:
                System.out.println("黄灯等");
                break;
            case 3:
                System.out.println("绿灯行");
                break;
        }
    }
}
```
最后是测试函数，调用了 ApplicationContext 的 publishEvent 方法：
```java
@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        ApplicationContext applicationContext = SpringApplication.run(DemoApplication.class, args);
        LightEvent lightEvent = new LightEvent(1);
        applicationContext.publishEvent(lightEvent);
    }

}
```
输出结果为：
```
红灯停
```
## 2、Spring 事件原理
Spring 事件体系基于 ApplicationContext 实现，其构建过程主要包含在 ApplicationContext 接口的抽象实现类 AbstractApplicationContext 中。AbstractApplicationContext 中持有了 applicationEventMulticaster 成员变量，其初始化（initApplicationEventMulticaster）以及事件监听器的注册（registerListeners）过程可以在 refresh 函数中看到：
```java
@Override
public void refresh() throws BeansException, IllegalStateException {
    synchronized (this.startupShutdownMonitor) {
        // ...
        // 初始化当前 ApplicationContext 的事件广播器
        initApplicationEventMulticaster();
        // ...
        // 注册事件监听器，监听器需要实现 ApplicationListener 接口
        registerListeners();
        // ...
    }
}
```
### 2.1 初始化事件广播
```java
//...
public static final String APPLICATION_EVENT_MULTICASTER_BEAN_NAME = "applicationEventMulticaster";
//...
 
protected void initApplicationEventMulticaster() {
    ConfigurableListableBeanFactory beanFactory = getBeanFactory();
    if (beanFactory.containsLocalBean(APPLICATION_EVENT_MULTICASTER_BEAN_NAME)) {
        this.applicationEventMulticaster =
                beanFactory.getBean(APPLICATION_EVENT_MULTICASTER_BEAN_NAME, ApplicationEventMulticaster.class);
        if (logger.isDebugEnabled()) {
            logger.debug("Using ApplicationEventMulticaster [" + this.applicationEventMulticaster + "]");
        }
    }
    else {
        this.applicationEventMulticaster = new SimpleApplicationEventMulticaster(beanFactory);
        beanFactory.registerSingleton(APPLICATION_EVENT_MULTICASTER_BEAN_NAME, this.applicationEventMulticaster);
        if (logger.isDebugEnabled()) {
            logger.debug("Unable to locate ApplicationEventMulticaster with name '" +
                    APPLICATION_EVENT_MULTICASTER_BEAN_NAME +
                    "': using default [" + this.applicationEventMulticaster + "]");
        }
    }
}
```
在初始化事件广播器的过程中，Spring 会首先检查是否存在用户自定义的名称为“applicationEventMulticaster”且实现了 ApplicationEventMulticaster 接口的 Bean。若存在则使用用户自定义的 ApplicationEventMulticaster 作为事件广播器，否则使用默认的 SimpleApplicationEventMulticaster。

### 2.2 注册事件监听器
```java
protected void registerListeners() {
    //...
    String[] listenerBeanNames = getBeanNamesForType(ApplicationListener.class, true, false);
    for (String listenerBeanName : listenerBeanNames) {
        getApplicationEventMulticaster().addApplicationListenerBean(listenerBeanName);
    }
    //...
}
```
最主要的步骤为通过反射获取所有实现了 ApplicationListener 接口的 Bean 的BeanName，并调用 addApplicationListenerBean 方法将其注册到 applicationEventMulticaster 中。addApplicationListenerBean 方法的实现在 AbstractApplicationEventMulticaster 中：
```java
public void addApplicationListenerBean(String listenerBeanName) {
    synchronized (this.retrievalMutex) {
        this.defaultRetriever.applicationListenerBeans.add(listenerBeanName);
        this.retrieverCache.clear();
    }
}
```
其中 ListenerRetriever 的数据结构如下，可以看到 applicationListenerBeans 中存放的是监听器的名字：
```java
private class ListenerRetriever {
    public final Set<ApplicationListener<?>> applicationListeners;
    public final Set<String> applicationListenerBeans;
    //..
}
```
这些注册在 applicationListenerBeans 的监听器的名字会在广播器获取监听器的时候通过 getBean 的方式加入到 applicationListeners。

### 2.3 发布事件
```java
public void publishEvent(Object event) {
    publishEvent(event, null);
}

protected void publishEvent(Object event, ResolvableType eventType) {
    Assert.notNull(event, "Event must not be null");
    if (logger.isTraceEnabled()) {
        logger.trace("Publishing event in " + getDisplayName() + ": " + event);
    }
 
    //...
 
    if (this.earlyApplicationEvents != null) {
        this.earlyApplicationEvents.add(applicationEvent);
    }
    else {
        getApplicationEventMulticaster().multicastEvent(applicationEvent, eventType);
    }
 
    //...
}
```
publishEvent(Object event) 最终调用了 publishEvent(Object event, ResolvableType eventType)，其中最关键的部分即调用了 applicationEventMulticaster的multicastEvent 方法，我们可以看一下 SimpleApplicationEventMulticaster 中 multicastEvent 方法的实现：
```java
public void multicastEvent(final ApplicationEvent event, ResolvableType eventType) {
    ResolvableType type = (eventType != null ? eventType : resolveDefaultEventType(event));
    for (final ApplicationListener<?> listener : getApplicationListeners(event, type)) {
        Executor executor = getTaskExecutor();
        if (executor != null) {
            executor.execute(new Runnable() {
                @Override
                public void run() {
                    invokeListener(listener, event);
                }
            });
        }
        else {
            invokeListener(listener, event);
        }
    }
}
//...
@SuppressWarnings({"unchecked", "rawtypes"})
protected void invokeListener(ApplicationListener listener, ApplicationEvent event) {
    ErrorHandler errorHandler = getErrorHandler();
    if (errorHandler != null) {
        try {
            listener.onApplicationEvent(event);
        }
        catch (Throwable err) {
            errorHandler.handleError(err);
        }
    }
    else {
        listener.onApplicationEvent(event);
    }
}
```
该方法获取所有注册了给定事件的监听器，默认情况下 executor 为null，因此会直接调用 invokeListener 方法，在该方法中调用了 listener 的 onApplicationEvent 方法，实现对事件监听器的通知，完成事件发布。这样默认的调用方式是同步的，主流程需要等待所有 listener 的 onApplictionEvent 方法执行完毕才能继续执行。

### 2.4 异步事件
通过源码我们可以知道事件广播器在广播前会检查是否传入了 executor，所以我们只需要在广播器中设置 Executor 属性就可以实现异步事件：
```java
SimpleApplicationEventMulticaster applicationEventMulticaster = applicationContext.getBean(SimpleApplicationEventMulticaster.class);
applicationEventMulticaster.setTaskExecutor(Executors.newCachedThreadPool());
```
## 3、基于注解的事件与异步事件
Spring 4.2 开始提供了@EventListener 注解，使得监听器不再需要实现 ApplicationListener 接口，只需要在监听方法上加上该注解即可，方法不一定叫 onApplicationEvent，但有且只能有一个参数，指定监听的事件类型。如：
```java
@EventListener
public void handler(LightEvent lightEvent) {
    //...
}
```
对于异步事件，Spring 3.0 开始提供了@Async 注解，可以方便快速地实现异步事件：
```java
@EventListener
@Async
public void handler(LightEvent lightEvent) {
    //..
}
```
### 3.1 @EventListener 原理
对于@EventListener 注解，实现的逻辑在这里：
```java
public void preInstantiateSingletons() throws BeansException {
     // ... 
     // 到这里说明所有的非懒加载的 singleton beans 已经完成了初始化
     // 如果我们定义的 bean 是实现了 SmartInitializingSingleton 接口的，那么在这里回调它的 afterSingletonsInstantiated 方法
     // 通过名字可以知道它表示单例对象初始化后需要做的操作
    for (String beanName : beanNames) {
        Object singletonInstance = getSingleton(beanName);
        if (singletonInstance instanceof SmartInitializingSingleton) {
            final SmartInitializingSingleton smartSingleton = (SmartInitializingSingleton) singletonInstance;
            if (System.getSecurityManager() != null) {
                AccessController.doPrivileged((PrivilegedAction<Object>) () -> {
                    smartSingleton.afterSingletonsInstantiated();
                    return null;
                }, getAccessControlContext());
            }
            else {
                smartSingleton.afterSingletonsInstantiated();
            }
        }
    }
}
```
这里有个实现了 SmartInitializingSingleton 接口的 EventListenerMethodProcessor 会被调用，它的 afterSingletonsInstantiated 方法如下：
```java
public void afterSingletonsInstantiated() {
   // 从 BeanFactory 中获取 EventListenerFactory 的 bean，默认是 DefaultEventListenerFactory
   List<EventListenerFactory> factories = getEventListenerFactories();
   ConfigurableApplicationContext context = getApplicationContext();
   String[] beanNames = context.getBeanNamesForType(Object.class);
   for (String beanName : beanNames) {
      // ...
       try {
           // 对所有 bean 进行处理
           processBean(factories, beanName, type);
       }
       catch (Throwable ex) {
           throw new BeanInitializationException("Failed to process @EventListener " +
                                                 "annotation on bean with name '" + beanName + "'", ex);
       }
   }
}
```
两个逻辑：
1. 从 BeanFactory 中获取 EventListenerFactory 的 bean，默认两种情况：
 1. DefaultEventListenerFactory  --- applicationContext 自己注入的
 2. TransactionalEventListenerFactory -- 使用配置进去的
2. 调用 processBean 对所有的 bean 进行处理

processBean 的逻辑如下：
```java
protected void processBean(final List<EventListenerFactory> factories, final String beanName, final Class<?> targetType) {
    // ...
    Map<Method, EventListener> annotatedMethods = null;
    // 查找当前 bean 标注了@EventListener 的方法
    annotatedMethods = MethodIntrospector.selectMethods(targetType,
            (MethodIntrospector.MetadataLookup<EventListener>) method ->
                AnnotatedElementUtils.findMergedAnnotation(method, EventListener.class));
    }
    // ...
    for (Method method : annotatedMethods.keySet()) {
        for (EventListenerFactory factory : factories) {
            if (factory.supportsMethod(method)) {
                Method methodToUse = AopUtils.selectInvocableMethod(method, context.getType(beanName));
                // 使用监听器工厂创建事件监听器
                ApplicationListener<?> applicationListener = factory.createApplicationListener(beanName, targetType, methodToUse);
                if (applicationListener instanceof ApplicationListenerMethodAdapter) {
                    ((ApplicationListenerMethodAdapter) applicationListener).init(context, this.evaluator);
                }
                // 注册事件到容器中
                context.addApplicationListener(applicationListener);
                break;
                }
            }
        }
        // ...
      }
   }
}
```
三个逻辑：
1. 查找当前 bean 标注了@EventListener 的方法
2. 使用监听器工厂创建事件监听器
3. 注册事件到容器中

监听器工厂创建事件监听器的逻辑如下：
```java
public ApplicationListener<?> createApplicationListener(String beanName, Class<?> type, Method method) {
   return new ApplicationListenerMethodAdapter(beanName, type, method);
}
```
返回的是一个 `ApplicationListenerMethodAdapter` 对象，这个 ApplicationListenerMethodAdapter 对象内部持有了 Method 且实现了 ApplicationListener 接口，它的 onApplicationEvent 方法就是调用相应 Method：
```java
@Override
public void onApplicationEvent(ApplicationEvent event) {
    processEvent(event);
}

public void processEvent(ApplicationEvent event) {
    Object[] args = resolveArguments(event);
    if (shouldHandle(event, args)) {
        Object result = doInvoke(args);
        if (result != null) {
            handleResult(result);
        }
     // ...
    }
}

protected Object doInvoke(Object... args) {
    //...
    try{
        // 调用 method 的方法
        return this.method.invoke(bean, args);
    }    
    // ...
}
```
最终，我们注释了@EventListener 的方法会被封装成 ApplicationListenerMethodAdapter 对象，它也是一个 ApplicationListener 对象，跟通过实现 ApplicationListener 接口的监听器一样被注册进容器，被广播器调用。调用的时候执行的就是原方法。

## 4、总结
Spring 中的事件机制是观察者模式的一个典型应用。Spring 会首先初始化事件广播器 ApplicationEventMulticaster，这个组件内部维护了一个事件监听器 ApplicationListener 的集合，事件监听器需要实现 onApplicationEvent 方法，这个方法有且只有一个参数就是 ApplicationEvent 的子类。当我们调用 applicationContext.publishEvent 发布事件的时候，本质上就是调用容器内部的事件广播器把它内部维护的监听器列表轮询一遍，依次调用各个监听器的 onApplicationEvent 方法。我们也可以给广播器传入一个线程池对象，这样广播器在调用各监听器的 onApplicationEvent 方法的时候会把它放在线程池里进行。注解@EventListener 可以指定一个方法为监听器方法，它的原理是在单例 bean 初始化之后，调用一个处理器来检查所有 bean 的方法是否包含@EventListener 注解（这里有一个容易搞错的地方就是处理器检查的时机是在单例 bean 初始化后没错，但检查的是所有的 bean，因为这是通过 beanName 来获取的，只要定义过的 bean 都会被检查到，不管是单例、多例还是懒加载），然后把这个方法包装成一个 ApplicationListener 注册到广播器中（这里又有一个容易搞错的地方就是这个 ApplicationListener 对象和持有方法的原对象是两个对象，原对象是单例还是多例、是创建出来了还是没创建出来，都不会影响生成  ApplicationListener，生成后就是单独的一个单例 bean）。@EventListener 定义的方法必须满足两点要求：一是只能有一个参数，二是参数必须继承 ApplicationEvent，否则会报错。