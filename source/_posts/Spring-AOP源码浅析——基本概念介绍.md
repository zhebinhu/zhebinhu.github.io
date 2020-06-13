---
title: Spring AOP 源码分析——基本概念介绍
tags: 
	- Spring
toc: true
date: 2019-03-14 20:41:41
---
AOP 全称是 Aspect Oriented Programming，即面向切面的编程，AOP 是一种开发理念。通过 AOP，我们可以把一些非业务逻辑的代码，比如安全检查，监控等代码从业务方法中抽取出来，以非侵入的方式与原方法进行协同。这样可以使原方法更专注于业务逻辑，代码结构会更加清晰，便于维护。Spring AOP 的原理很简单，就是动态代理，它和 AspectJ 不一样，AspectJ 是直接修改掉你的字节码。但 Spring 中仍然沿用了 AspectJ 的概念，它分为五个部分：连接点、切点、通知、切面和织入。我们通过一次实际 AOP 的使用来说明这五个部分。

## 1、连接点 - Joinpoint
连接点是指程序执行过程中的一些点，比如方法调用，异常处理等。在 Spring AOP 中，仅支持方法级别的连接点。上面是官方的概念，下面举个实际的例子。现在我们有一个 Car 接口，该接口定义如下：
```java
public interface Car {
    public void run();
    public void stop();
}
```
它有一个实现类，这个实现类的定义如下：
```java
@Component("car")
public class CarImpl implements Car{
    @Override
    public void run(){
        System.out.println("car run...");
    }

    @Override
    public void stop() {
        System.out.println("car stop");
    }
}
```
现在我们在别的地方调用这个对象：
```java
@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        ApplicationContext applicationContext = SpringApplication.run(DemoApplication.class, args);
        Car car = (Car)applicationContext.getBean("car");
        car.run(); // 连接点1
        car.stop(); // 连接点2
    }

}
```
如上所示，每次方法调用都是一个连接点。Spring 中把连接点抽象成了一个接口，可以获取当前调用方法的各种信息：
```java
public interface JoinPoint {  
    String toString();         // 连接点所在位置的相关信息  
    String toShortString();     // 连接点所在位置的简短相关信息  
    String toLongString();     // 连接点所在位置的全部相关信息  
    Object getThis();         // 返回AOP代理对象  
    Object getTarget();       // 返回目标对象  
    Object[] getArgs();       // 返回被通知方法参数列表  
    Signature getSignature();  // 返回当前连接点签名  
    SourceLocation getSourceLocation();// 返回连接点方法所在类文件中的位置  
    String getKind();        // 连接点类型  
    StaticPart getStaticPart(); // 返回连接点静态部分  
}  
```
## 2、切点 - Pointcut
切点的作用是选出合适的连接点。我们可以定义一个切点：
```java
@Pointcut("execution(* com.huzb.demo.CarImpl.run(..))")
public void pointCut(){}
```
切点是个空方法，使用@Pointcut 注解表示这是一个切点，注解的 value 是个 execution 表达式，有专门的语法，用于匹配连接点。

## 3、通知 - Advice
通知 Advice 即我们定义的横切逻辑，比如我们可以定义一个用于监控方法性能的通知，也可以定义一个安全检查的通知等。如果说切点解决了通知在哪里调用的问题，那么现在还需要考虑了一个问题，即通知在何时被调用？是在目标方法前被调用，还是在目标方法返回后被调用，还在两者兼备呢？Spring 帮我们解答了这个问题，Spring 中定义了以下几种通知类型：
- 前置通知（@Before）- 在目标方便调用前执行通知
- 后置通知（@After）- 在目标方法完成后执行通知
- 返回通知（@AfterReturning）- 在目标方法执行成功后，调用通知
- 异常通知（@AfterThrowing）- 在目标方法抛出异常后，执行通知
- 环绕通知（@Around）- 在目标方法调用前后均可执行自定义逻辑

我们来尝试自定义一个通知：
```java
@Before("com.huzb.demo.LogAspect.pointCut()")
public void logStart(JoinPoint joinPoint) {
    Object[] args = joinPoint.getArgs();
    System.out.println("方法调用之前");
}
```
@Before 注释表明了这是一个前置通知，注释中的 value 指定了切点，所以这个通知只会在切点指定的方法调用前执行。参数表的第一个是 JoinPoint 对象，也就是连接点对象，从中我们可以获取到调用方法的参数列表、所属实例等信息。参数列表中也可以没有 JoinPoint 对象，但如果要获取 JoinPoint，就一定要把它放在第一个，不然 Spring 不会自动注入。另外还有其它类型的通知，有些使用方法和前置通知略有不同，如下所示：
```java
@After("com.huzb.demo.LogAspect.pointCut()")
public void logEnd(JoinPoint joinPoint) {
    System.out.println("方法调用之后");
}

// 把返回对象注入到参数列表中的 result
@AfterReturning(value = "com.huzb.demo.LogAspect.pointCut()", returning = "result")
public void logReturn(JoinPoint joinPoint, Object result) {
    System.out.println("方法返回的结果为：" + result);
}

// 把抛出的异常注入到参数列表中的 exception
@AfterThrowing(value = "com.huzb.demo.LogAspect.pointCut()", throwing = "exception")
public void logException(JoinPoint joinPoint, Exception exception) {
    System.out.println("方法抛出的异常为：" + exception.getMessage());
}

@Around("com.huzb.demo.LogAspect.pointCut()")
public void logAround(ProceedingJoinPoint joinPoint) {
    Object result;
    System.out.println("方法调用之前");
    try {
        result = joinPoint.proceed(); // 手动执行方法
        System.out.println("方法返回的结果为：" + result);
    } catch (Throwable throwable) {
        System.out.println("方法抛出的异常为：" + throwable.getMessage());
    }
    System.out.println("方法调用之后");
}
```

## 4、切面 - Aspect
有了切点和通知，我们需要把它们整合起来，这个整合的工具就是切面。我们可以为刚才创建的切点和通知定义一个切面：
```java
@Component
@Aspect
public class LogAspect {
    @Pointcut("execution(* com.huzb.demo.CarImpl.run(..))")
    public void pointCut() {
    }

    @Before("pointCut()")
    public void logStart(JoinPoint joinPoint) {
        Object[] args = joinPoint.getArgs();
        System.out.println("方法调用之前");
    }

    @After("pointCut()")
    public void logEnd(JoinPoint joinPoint) {
        System.out.println("方法调用之后");
    }

    // 把返回对象注入到参数列表中的 result
    @AfterReturning(value = "pointCut()", returning = "result")
    public void logReturn(JoinPoint joinPoint, Object result) {
        System.out.println("方法返回的结果为：" + result);
    }

    // 把抛出的异常注入到参数列表中的 exception
    @AfterThrowing(value = "pointCut()", throwing = "exception")
    public void logException(JoinPoint joinPoint, Exception exception) {
        System.out.println("方法抛出的异常为：" + exception.getMessage());
    }
}
```
LogAspect 类上的注释@Aspect 表明这是一个切面类，切面类一定要声明为一个 bean 加入 IOC 容器中，否则切面类不会生效。

## 5、织入 - Weaving
现在我们有了连接点、切点、通知，以及切面等，可谓万事俱备，但是还差了一股东风。这股东风是什么呢？没错，就是织入。所谓织入就是在切点的引导下，将通知逻辑插入到方法调用上，使得我们的通知逻辑在方法调用时得以执行。说完织入的概念，现在来说说 Spring 是通过何种方式将通知织入到目标方法上的。先来说说以何种方式进行织入，这个方式就是通过实现后置处理器 BeanPostProcessor 接口。该接口是 Spring 提供的一个拓展接口，通过实现该接口，用户可在 bean 初始化前后做一些自定义操作。那 Spring 是在何时进行织入操作的呢？答案是在 bean 初始化完成后，即 bean 执行完初始化方法（init-method）。Spring 通过切点对 bean 类中的方法进行匹配。若匹配成功，则会为该 bean 生成代理对象，并将代理对象返回给容器。容器向后置处理器输入 bean 对象，得到 bean 对象的代理，这样就完成了织入过程。

## 运行结果
调用 `car.run()` 方法，我们会得到以下结果：

<img src="./Spring-AOP源码浅析——基本概念介绍/运行结果.png"/>

说明我们的通知已经织入成功了。