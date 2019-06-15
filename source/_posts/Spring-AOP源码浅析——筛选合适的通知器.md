---
title: Spring AOP 源码浅析——筛选合适的通知器
tags: 
	- Java
	- Spring
toc: true
date: 2019-03-19 15:33:18
---
上篇我们讲过了 AOP 的概念和使用方式。这篇就开始进行源码分析。

## 1、AOP 入口分析

上篇我们提到过，AOP 在 Spring 中是通过后置处理器的方式织入到对应的 bean 中的。负责这部分逻辑的是后置处理器 `AnnotationAwareAspectJAutoProxyCreator` ，但由于 AnnotationAwareAspectJAutoProxyCreator 中没有覆写父类的 `postProcessAfterInitialization` 方法，所以我们找到的入口在它的父类 `AbstractAutoProxyCreator` 中，如下：
```java
public abstract class AbstractAutoProxyCreator extends ProxyProcessorSupport
        implements SmartInstantiationAwareBeanPostProcessor, BeanFactoryAware {
    
    @Override
    /** bean 初始化后置处理方法 */
    public Object postProcessAfterInitialization(Object bean, String beanName) throws BeansException {
        if (bean != null) {
            Object cacheKey = getCacheKey(bean.getClass(), beanName);
            if (!this.earlyProxyReferences.contains(cacheKey)) {
                // 如果需要，为 bean 生成代理对象
                return wrapIfNecessary(bean, beanName, cacheKey);
            }
        }
        return bean;
    }
    
    protected Object wrapIfNecessary(Object bean, String beanName, Object cacheKey) {
        if (beanName != null && this.targetSourcedBeans.contains(beanName)) {
            return bean;
        }
        if (Boolean.FALSE.equals(this.advisedBeans.get(cacheKey))) {
            return bean;
        }

        // 如果是基础设施类（Pointcut、Advice、Advisor 等接口的实现类），或是应该跳过的类，则不应该生成代理，此时直接返回 bean
        if (isInfrastructureClass(bean.getClass()) || shouldSkip(bean.getClass(), beanName)) {
            // 将 <cacheKey, FALSE> 键值对放入缓存中，供上面的 if 分支使用
            this.advisedBeans.put(cacheKey, Boolean.FALSE);
            return bean;
        }

        // 为目标 bean 查找合适的通知器
        Object[] specificInterceptors = getAdvicesAndAdvisorsForBean(bean.getClass(), beanName, null);
        // 若 specificInterceptors != null，即 specificInterceptors != DO_NOT_PROXY，则为 bean 生成代理对象，否则直接返回 bean
        if (specificInterceptors != DO_NOT_PROXY) {
            this.advisedBeans.put(cacheKey, Boolean.TRUE);
            // 创建代理
            Object proxy = createProxy(bean.getClass(), beanName, specificInterceptors, new SingletonTargetSource(bean));
            this.proxyTypes.put(cacheKey, proxy.getClass());
            // 返回代理对象
            return proxy;
        }

        this.advisedBeans.put(cacheKey, Boolean.FALSE);
        // specificInterceptors = null，直接返回 bean
        return bean;
    }
}
```
以上就是 Spring AOP 创建代理对象的入口方法分析，过程比较简单，这里简单总结一下：
1. 若 bean 是 AOP 基础设施类型，则直接返回
2. 为 bean 筛选合适的通知器
3. 如果通知器数组不为空，则为 bean 生成代理对象，并返回该对象
4. 若数组为空，则返回原始 bean

上面的流程看起来并不复杂，不过不要被表象所迷糊，以上流程不过是冰山一角。`筛选合适的通知器`和`生成代理对象`这两步将是我们重点关注的。

## 2、查找合适的通知器
在向目标 bean 中织入通知之前，我们先要为 bean 筛选出合适的通知器（通知器持有通知）。如何筛选呢？方式有很多，比如我们可以通过正则表达式匹配方法名，当然更多的时候用的是 AspectJ 表达式进行匹配。那下面我们就来看一下使用 AspectJ 表达式筛选通知器的过程，如下：
```java
protected Object[] getAdvicesAndAdvisorsForBean(Class<?> beanClass, String beanName, TargetSource targetSource) {
    // 查找合适的通知器
    List<Advisor> advisors = findEligibleAdvisors(beanClass, beanName);
    if (advisors.isEmpty()) {
        return DO_NOT_PROXY;
    }
    return advisors.toArray();
}

protected List<Advisor> findEligibleAdvisors(Class<?> beanClass, String beanName) {
    // 查找所有的通知器
    List<Advisor> candidateAdvisors = findCandidateAdvisors();
    // 筛选可应用在 beanClass 上的 Advisor，通过 ClassFilter 和 MethodMatcher 对目标类和方法进行匹配
    List<Advisor> eligibleAdvisors = findAdvisorsThatCanApply(candidateAdvisors, beanClass, beanName);
    // 拓展操作
    extendAdvisors(eligibleAdvisors);
    if (!eligibleAdvisors.isEmpty()) {
        eligibleAdvisors = sortAdvisors(eligibleAdvisors);
    }
    return eligibleAdvisors;
}
```
### 2.1 查找所有的通知器
Spring 提供了两种配置 AOP 的方式，一种是通过 XML 进行配置，另一种是注解。对于两种配置方式，Spring 的处理逻辑是不同的。如下面的 xml 方式的配置：
```java
public class LogBeforeAdvice implements MethodBeforeAdvice{

    @Override
    public void before(Method method, Object[] args, Object target) throws Throwable {
        System.out.println("方法调用之前");
    }
}
```
```xml
<bean id="logBeforeAdvice" class="com.huzb.demo.LogBeforeAdvice"/>

<bean id="logBeforeAdvisor" class="org.springframework.aop.aspectj.AspectJExpressionPointcutAdvisor">  
    <property name="advice" ref="logBeforeAdvice" />  
    <property name="expression" value="execution(* com.huzb.demo.CarImpl.run(..))" />   
</bean>

<!--使所有Advisor生效-->
<bean class="org.springframework.aop.framework.autoproxy.DefaultAdvisorAutoProxyCreator" />
```
它和下面的注解方式是等价的：
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

    @AfterReturning(value = "pointCut()", returning = "result")
    public void logReturn(JoinPoint joinPoint, Object result) {
        System.out.println("方法返回的结果为：" + result.toString());
    }
}
```
上述两种配置下，Spring 除了生成一个普通的 bean 对象外，还会生成一个类型为 AspectJExpressionPointcut 的对象和两个类型为 AspectJPointcutAdvisor（注意不是 Advice，是 Advisor，这是一种只包含一个 Advice 和一个 Pointcut 的特殊切面，可以叫它通知器） 的对象，分别表示切点和通知器。也就是说，在 Spring 中，切点和通知器是被当成单独的 bean 加入容器的，尽管它们可能并不作为一个类被定义。下面让我们看一下源码：
```java
public class AnnotationAwareAspectJAutoProxyCreator extends AspectJAwareAdvisorAutoProxyCreator {

    //...

    @Override
    protected List<Advisor> findCandidateAdvisors() {
        // 调用父类方法从容器中查找类型为 Advisor 的通知器
        List<Advisor> advisors = super.findCandidateAdvisors();
        // 解析 @Aspect 注解，并构建通知器
        advisors.addAll(this.aspectJAdvisorsBuilder.buildAspectJAdvisors());
        return advisors;
    }

    //...
}
```
AnnotationAwareAspectJAutoProxyCreator 覆写了父类的方法 findCandidateAdvisors，并增加了一步操作，即解析 @Aspect 注解，并构建成通知器。下面我们先来分析一下父类中的 findCandidateAdvisors 方法的逻辑，然后再来分析 buildAspectJAdvisors 方法的逻辑。

#### 2.1.1 findCandidateAdvisors 方法分析

我们先来看一下 AbstractAdvisorAutoProxyCreator 中 findCandidateAdvisors 方法的定义，如下：
```java
public abstract class AbstractAdvisorAutoProxyCreator extends AbstractAutoProxyCreator {

    private BeanFactoryAdvisorRetrievalHelper advisorRetrievalHelper;
    
    //...

    protected List<Advisor> findCandidateAdvisors() {
        return this.advisorRetrievalHelper.findAdvisorBeans();
    }

    //...
}
```
从上面的源码中可以看出，AbstractAdvisorAutoProxyCreator 中的 findCandidateAdvisors 是个空壳方法，所有逻辑封装在了一个 BeanFactoryAdvisorRetrievalHelper 的 findAdvisorBeans 方法中。这里大家可以仔细看一下类名 BeanFactoryAdvisorRetrievalHelper 和方法 findAdvisorBeans，两个名字其实已经描述出他们的职责了。BeanFactoryAdvisorRetrievalHelper 可以理解为从 bean 容器中获取 Advisor 的帮助类，findAdvisorBeans 则可理解为查找 Advisor 类型的 bean。所以即使不看 findAdvisorBeans 方法的源码，我们也可从方法名上推断出它要做什么，即从 bean 容器中将 Advisor 类型的 bean 查找出来。下面我们来分析一下这个方法的源码，如下：
```java
public List<Advisor> findAdvisorBeans() {
    String[] advisorNames = null;
    synchronized (this) {
        // cachedAdvisorBeanNames 是 advisor 名称的缓存
        advisorNames = this.cachedAdvisorBeanNames;
        // 如果 cachedAdvisorBeanNames 为空，这里到容器中查找，并设置缓存，后续直接使用缓存即可
        if (advisorNames == null) {
            // 从容器中查找所有 Advisor 类型 bean 的名称
            advisorNames = BeanFactoryUtils.beanNamesForTypeIncludingAncestors(this.beanFactory, Advisor.class, true, false);
            // 设置缓存
            this.cachedAdvisorBeanNames = advisorNames;
        }
    }
    if (advisorNames.length == 0) {
        return new LinkedList<Advisor>();
    }

    List<Advisor> advisors = new LinkedList<Advisor>();
    // 遍历 advisorNames
    for (String name : advisorNames) {
        if (isEligibleBean(name)) {
            // 忽略正在创建中的 advisor bean
            if (this.beanFactory.isCurrentlyInCreation(name)) {
                if (logger.isDebugEnabled()) {
                    logger.debug("Skipping currently created advisor '" + name + "'");
                }
            }
            else {
                try {
                    // 调用 getBean 方法从容器中获取或创建名称为 name 的 bean，并将 bean 添加到 advisors 中
                    advisors.add(this.beanFactory.getBean(name, Advisor.class));
                }
                catch (BeanCreationException ex) {
                    Throwable rootCause = ex.getMostSpecificCause();
                    if (rootCause instanceof BeanCurrentlyInCreationException) {
                        BeanCreationException bce = (BeanCreationException) rootCause;
                        if (this.beanFactory.isCurrentlyInCreation(bce.getBeanName())) {
                            if (logger.isDebugEnabled()) {
                                logger.debug("Skipping advisor '" + name +
                                        "' with dependency on currently created bean: " + ex.getMessage());
                            }
                            continue;
                        }
                    }
                    throw ex;
                }
            }
        }
    }

    return advisors;
}
```
以上就是从容器中查找 Advisor 类型的 bean 所有的逻辑，代码虽然有点长，但并不复杂。主要做了三件事情：
1. 从缓存中获取所有 Advisor 的名称
2. 如果缓存中没有，就从容器中查找所有类型为 Advisor 的 bean 对应的名称，然后放入缓存
3. 遍历 advisorNames，使用 getBean 方法创建或从容器中获取对应的 bean

看完上面的分析，我们继续来分析一下 @Aspect 注解的解析过程。

#### 2.1.2 buildAspectJAdvisors 方法分析
```java
public List<Advisor> buildAspectJAdvisors() {
    // aspectNames 中存放的是包含 Aspect 注解的类名，这个值不为空说明已经解析过
    List<String> aspectNames = this.aspectBeanNames;

    // 缓存中没有说明还未初始化，则先初始化
    if (aspectNames == null) {
        synchronized (this) {
            aspectNames = this.aspectBeanNames;
            if (aspectNames == null) {
                List<Advisor> advisors = new LinkedList<Advisor>();
                aspectNames = new LinkedList<String>();
                // 从容器中获取所有 bean 的名称
                String[] beanNames = BeanFactoryUtils.beanNamesForTypeIncludingAncestors(
                        this.beanFactory, Object.class, true, false);
                // 遍历 beanNames
                for (String beanName : beanNames) {
                    if (!isEligibleBean(beanName)) {
                        continue;
                    }
                    
                    // 根据 beanName 获取 bean 的类型
                    Class<?> beanType = this.beanFactory.getType(beanName);
                    if (beanType == null) {
                        continue;
                    }

                    // 检测 beanType 是否包含 Aspect 注解
                    if (this.advisorFactory.isAspect(beanType)) {
                        aspectNames.add(beanName);
                        AspectMetadata amd = new AspectMetadata(beanType, beanName);
                        if (amd.getAjType().getPerClause().getKind() == PerClauseKind.SINGLETON) {
                            MetadataAwareAspectInstanceFactory factory =
                                    new BeanFactoryAspectInstanceFactory(this.beanFactory, beanName);

                            // 获取通知器
                            List<Advisor> classAdvisors = this.advisorFactory.getAdvisors(factory);
                            if (this.beanFactory.isSingleton(beanName)) {
                                // 一个包含 Aspect 注解对应多个 Advisor，将这些 Advisor 缓存起来
                                this.advisorsCache.put(beanName, classAdvisors);
                            }
                            else {
                                this.aspectFactoryCache.put(beanName, factory);
                            }
                            advisors.addAll(classAdvisors);
                        }
                        else {
                            if (this.beanFactory.isSingleton(beanName)) {
                                throw new IllegalArgumentException("Bean with name '" + beanName +
                                        "' is a singleton, but aspect instantiation model is not singleton");
                            }
                            MetadataAwareAspectInstanceFactory factory =
                                    new PrototypeAspectInstanceFactory(this.beanFactory, beanName);
                            this.aspectFactoryCache.put(beanName, factory);
                            advisors.addAll(this.advisorFactory.getAdvisors(factory));
                        }
                    }
                }
                // 将包含 Aspect 注解的类名保存起来，避免重复解析
                this.aspectBeanNames = aspectNames;
                return advisors;
            }
        }
    }

    if (aspectNames.isEmpty()) {
        return Collections.emptyList();
    }
    List<Advisor> advisors = new LinkedList<Advisor>();
    for (String aspectName : aspectNames) {
        // 从缓存中获取
        List<Advisor> cachedAdvisors = this.advisorsCache.get(aspectName);
        if (cachedAdvisors != null) {
            advisors.addAll(cachedAdvisors);
        }
        else {
            MetadataAwareAspectInstanceFactory factory = this.aspectFactoryCache.get(aspectName);
            advisors.addAll(this.advisorFactory.getAdvisors(factory));
        }
    }
    return advisors;
}
```
上面就是 buildAspectJAdvisors 的代码，看起来比较长。代码比较多，我们关注重点的方法调用即可。在进行后续的分析前，这里先对 buildAspectJAdvisors 方法的执行流程做个总结。如下：
1. 检查是否已经解析过，已经解析过的话拿到所有包含 Aspect 注解的类名，跳到步骤6
2. 获取容器中所有 bean 的名称（beanName）和类型
3. 根据 beanType 判断当前 bean 是否是一个包含 Aspect 注解的类，如果是的话调用 advisorFactory.getAdvisors 获取通知器
4. 将通知器保存在缓存中
5. 设置 this.aspectBeanNames 为所有包含 Aspect 注解的类名
6. 按 this.aspectBeanNames 从缓存中获取所有通知器

下面我们来重点分析 `advisorFactory.getAdvisors(factory)` 这个调用，如下：
```java
public List<Advisor> getAdvisors(MetadataAwareAspectInstanceFactory aspectInstanceFactory) {
    // 获取 aspectClass 和 aspectName
    Class<?> aspectClass = aspectInstanceFactory.getAspectMetadata().getAspectClass();
    String aspectName = aspectInstanceFactory.getAspectMetadata().getAspectName();
    validate(aspectClass);

    MetadataAwareAspectInstanceFactory lazySingletonAspectInstanceFactory =
            new LazySingletonAspectInstanceFactoryDecorator(aspectInstanceFactory);

    List<Advisor> advisors = new LinkedList<Advisor>();

    // getAdvisorMethods 用于返回不包含 @Pointcut 注解的方法
    for (Method method : getAdvisorMethods(aspectClass)) {
        // 为每个方法分别调用 getAdvisor 方法
        Advisor advisor = getAdvisor(method, lazySingletonAspectInstanceFactory, advisors.size(), aspectName);
        if (advisor != null) {
            advisors.add(advisor);
        }
    }

    // If it's a per target aspect, emit the dummy instantiating aspect.
    if (!advisors.isEmpty() && lazySingletonAspectInstanceFactory.getAspectMetadata().isLazilyInstantiated()) {
        Advisor instantiationAdvisor = new SyntheticInstantiationAdvisor(lazySingletonAspectInstanceFactory);
        advisors.add(0, instantiationAdvisor);
    }

    // Find introduction fields.
    for (Field field : aspectClass.getDeclaredFields()) {
        Advisor advisor = getDeclareParentsAdvisor(field);
        if (advisor != null) {
            advisors.add(advisor);
        }
    }

    return advisors;
}

public Advisor getAdvisor(Method candidateAdviceMethod, MetadataAwareAspectInstanceFactory aspectInstanceFactory,
        int declarationOrderInAspect, String aspectName) {

    validate(aspectInstanceFactory.getAspectMetadata().getAspectClass());

    // 获取切点实现类
    AspectJExpressionPointcut expressionPointcut = getPointcut(
            candidateAdviceMethod, aspectInstanceFactory.getAspectMetadata().getAspectClass());
    if (expressionPointcut == null) {
        return null;
    }

    // 创建 Advisor 实现类
    return new InstantiationModelAwarePointcutAdvisorImpl(expressionPointcut, candidateAdviceMethod,
            this, aspectInstanceFactory, declarationOrderInAspect, aspectName);
}
```
如上，getAdvisor 方法包含两个主要步骤，一个是获取 AspectJ 表达式切点，另一个是创建 Advisor 实现类。在第二个步骤中，包含一个隐藏步骤 – 创建 Advice。下面我将按顺序依次分析这两个步骤，先看获取 AspectJ 表达式切点的过程，如下：
```java
private AspectJExpressionPointcut getPointcut(Method candidateAdviceMethod, Class<?> candidateAspectClass) {
    // 获取方法上的 AspectJ 相关注解，包括 @Before，@After 等
    AspectJAnnotation<?> aspectJAnnotation =
            AbstractAspectJAdvisorFactory.findAspectJAnnotationOnMethod(candidateAdviceMethod);
    if (aspectJAnnotation == null) {
        return null;
    }

    // 创建一个 AspectJExpressionPointcut 对象
    AspectJExpressionPointcut ajexp =
            new AspectJExpressionPointcut(candidateAspectClass, new String[0], new Class<?>[0]);
    // 找到其中的切点表达式，设置到 AspectJExpressionPointcut 对象
    ajexp.setExpression(aspectJAnnotation.getPointcutExpression());
    ajexp.setBeanFactory(this.beanFactory);
    return ajexp;
}

protected static AspectJAnnotation<?> findAspectJAnnotationOnMethod(Method method) {
    // classesToLookFor 中的元素是大家熟悉的
    Class<?>[] classesToLookFor = new Class<?>[] {
            Before.class, Around.class, After.class, AfterReturning.class, AfterThrowing.class, Pointcut.class};
    for (Class<?> c : classesToLookFor) {
        // 查找注解
        AspectJAnnotation<?> foundAnnotation = findAnnotation(method, (Class<Annotation>) c);
        if (foundAnnotation != null) {
            return foundAnnotation;
        }
    }
    return null;
}
```
获取切点的过程并不复杂，不过需要注意的是，目前获取到的切点可能还只是个半成品，需要再次处理一下才行。比如下面的代码：
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
}
```
@Before 注解中的表达式是pointcut()，也就是说 ajexp 设置的表达式只是一个中间值，不是最终值。所以后续还需要将 ajexp 中的表达式进行转换，关于这个转换的过程非常复杂，也不是重点，这里就不展开了。
说完切点的获取过程，下面再来看看 Advisor 实现类的创建过程。如下：
```java
public InstantiationModelAwarePointcutAdvisorImpl(AspectJExpressionPointcut declaredPointcut,
        Method aspectJAdviceMethod, AspectJAdvisorFactory aspectJAdvisorFactory,
        MetadataAwareAspectInstanceFactory aspectInstanceFactory, int declarationOrder, String aspectName) {

    this.declaredPointcut = declaredPointcut;
    this.declaringClass = aspectJAdviceMethod.getDeclaringClass();
    this.methodName = aspectJAdviceMethod.getName();
    this.parameterTypes = aspectJAdviceMethod.getParameterTypes();
    this.aspectJAdviceMethod = aspectJAdviceMethod;
    this.aspectJAdvisorFactory = aspectJAdvisorFactory;
    this.aspectInstanceFactory = aspectInstanceFactory;
    this.declarationOrder = declarationOrder;
    this.aspectName = aspectName;

    if (aspectInstanceFactory.getAspectMetadata().isLazilyInstantiated()) {
        Pointcut preInstantiationPointcut = Pointcuts.union(
                aspectInstanceFactory.getAspectMetadata().getPerClausePointcut(), this.declaredPointcut);

        this.pointcut = new PerTargetInstantiationModelPointcut(
                this.declaredPointcut, preInstantiationPointcut, aspectInstanceFactory);
        this.lazy = true;
    }
    else {
        this.pointcut = this.declaredPointcut;
        this.lazy = false;

        // 按照注解解析 Advice
        this.instantiatedAdvice = instantiateAdvice(this.declaredPointcut);
    }
}
```
上面是 InstantiationModelAwarePointcutAdvisorImpl 的构造方法，不过我们无需太关心这个方法中的一些初始化逻辑。我们把目光移到构造方法的最后一行代码中，即 instantiateAdvice(this.declaredPointcut)，这个方法用于创建通知 Advice。我们之前提到过，通知器 Advisor 是通知 Advice 的持有者，所以在 Advisor 实现类的构造方法中创建通知也是合适的。那下面我们就来看看构建通知的过程是怎样的，如下：
```java
private Advice instantiateAdvice(AspectJExpressionPointcut pcut) {
    return this.aspectJAdvisorFactory.getAdvice(this.aspectJAdviceMethod, pcut,
            this.aspectInstanceFactory, this.declarationOrder, this.aspectName);
}

public Advice getAdvice(Method candidateAdviceMethod, AspectJExpressionPointcut expressionPointcut,
        MetadataAwareAspectInstanceFactory aspectInstanceFactory, int declarationOrder, String aspectName) {

    Class<?> candidateAspectClass = aspectInstanceFactory.getAspectMetadata().getAspectClass();
    validate(candidateAspectClass);

    // 获取 Advice 注解
    AspectJAnnotation<?> aspectJAnnotation = AbstractAspectJAdvisorFactory.findAspectJAnnotationOnMethod(candidateAdviceMethod);
    if (aspectJAnnotation == null) {
        return null;
    }

    if (!isAspect(candidateAspectClass)) {
        throw new AopConfigException("Advice must be declared inside an aspect type: Offending method '" + candidateAdviceMethod + "' in class [" +
                candidateAspectClass.getName() + "]");
    }

    if (logger.isDebugEnabled()) {
        logger.debug("Found AspectJ method: " + candidateAdviceMethod);
    }

    AbstractAspectJAdvice springAdvice;

    // 按照注解类型生成相应的 Advice 实现类
    switch (aspectJAnnotation.getAnnotationType()) {
        case AtBefore:    // @Before -> AspectJMethodBeforeAdvice
            springAdvice = new AspectJMethodBeforeAdvice(candidateAdviceMethod, expressionPointcut, aspectInstanceFactory);
            break;

        case AtAfter:    // @After -> AspectJAfterAdvice
            springAdvice = new AspectJAfterAdvice(candidateAdviceMethod, expressionPointcut, aspectInstanceFactory);
            break;

        case AtAfterReturning:    // @AfterReturning -> AspectJAfterAdvice
            springAdvice = new AspectJAfterReturningAdvice(candidateAdviceMethod, expressionPointcut, aspectInstanceFactory);
            AfterReturning afterReturningAnnotation = (AfterReturning) aspectJAnnotation.getAnnotation();
            if (StringUtils.hasText(afterReturningAnnotation.returning())) {
                springAdvice.setReturningName(afterReturningAnnotation.returning());
            }
            break;

        case AtAfterThrowing:    // @AfterThrowing -> AspectJAfterThrowingAdvice
            springAdvice = new AspectJAfterThrowingAdvice(candidateAdviceMethod, expressionPointcut, aspectInstanceFactory);
            AfterThrowing afterThrowingAnnotation = (AfterThrowing) aspectJAnnotation.getAnnotation();
            if (StringUtils.hasText(afterThrowingAnnotation.throwing())) {
                springAdvice.setThrowingName(afterThrowingAnnotation.throwing());
            }
            break;

        case AtAround:    // @Around -> AspectJAroundAdvice
            springAdvice = new AspectJAroundAdvice(candidateAdviceMethod, expressionPointcut, aspectInstanceFactory);
            break;

        /*
         * 如果注解类型为 AtPointcut 的情况，什么都不做，直接返回 null。
         * 从整个方法的调用栈来看，并不会出现注解类型为 AtPointcut 的情况
         */ 
        case AtPointcut:    
            if (logger.isDebugEnabled()) {
                logger.debug("Processing pointcut '" + candidateAdviceMethod.getName() + "'");
            }
            return null;
            
        default:
            throw new UnsupportedOperationException(
                    "Unsupported advice type on method: " + candidateAdviceMethod);
    }

    springAdvice.setAspectName(aspectName);
    springAdvice.setDeclarationOrder(declarationOrder);
    /*
     * 获取方法的参数列表名称，比如方法 int sum(int numX, int numY), 
     * getParameterNames(sum) 得到 argNames = ["numX", "numY"]
     */
    String[] argNames = this.parameterNameDiscoverer.getParameterNames(candidateAdviceMethod);
    if (argNames != null) {
        // 设置参数名
        springAdvice.setArgumentNamesFromStringArray(argNames);
    }
    springAdvice.calculateArgumentBindings();
    return springAdvice;
}
```
上面的代码逻辑不是很复杂，主要的逻辑就是根据注解类型生成与之对应的通知对象。下面来总结一下获取通知器（getAdvisors）整个过程的逻辑，如下：
1. 从目标 bean 中获取不包含 Pointcut 注解的方法列表
2. 遍历上一步获取的方法列表，并调用 getAdvisor 获取当前方法对应的 Advisor
3. 创建 AspectJExpressionPointcut 对象，并从方法中的注解中获取表达式，设置到切点对象中
4. 创建 Advisor 实现类对象 InstantiationModelAwarePointcutAdvisorImpl
5. 调用 instantiateAdvice 方法构建通知
6. 调用 getAdvice 方法，并根据注解类型创建相应的通知

如上所示，上面的步骤做了一定的简化。总的来说，获取通知器的过程还是比较复杂的，并不是很容易看懂。现在，大家知道了通知是怎么创建的。那我们难道不要去看看这些通知的实现源码吗？显然，我们应该看一下。那接下里，我们一起来分析一下 AspectJMethodBeforeAdvice，也就是 @Before 注解对应的通知实现类。看看它的逻辑是什么样的。

2.1.3 AspectJMethodBeforeAdvice 分析
```java
public class AspectJMethodBeforeAdvice extends AbstractAspectJAdvice implements MethodBeforeAdvice {

    public AspectJMethodBeforeAdvice(
            Method aspectJBeforeAdviceMethod, AspectJExpressionPointcut pointcut, AspectInstanceFactory aif) {

        super(aspectJBeforeAdviceMethod, pointcut, aif);
    }


    @Override
    public void before(Method method, Object[] args, Object target) throws Throwable {
        // 调用通知方法
        invokeAdviceMethod(getJoinPointMatch(), null, null);
    }

    @Override
    public boolean isBeforeAdvice() {
        return true;
    }

    @Override
    public boolean isAfterAdvice() {
        return false;
    }

}

protected Object invokeAdviceMethod(JoinPointMatch jpMatch, Object returnValue, Throwable ex) throws Throwable {
    // 调用通知方法，并向其传递参数
    return invokeAdviceMethodWithGivenArgs(argBinding(getJoinPoint(), jpMatch, returnValue, ex));
}

protected Object invokeAdviceMethodWithGivenArgs(Object[] args) throws Throwable {
    Object[] actualArgs = args;
    if (this.aspectJAdviceMethod.getParameterTypes().length == 0) {
        actualArgs = null;
    }
    try {
        ReflectionUtils.makeAccessible(this.aspectJAdviceMethod);
        // 通过反射调用通知方法
        return this.aspectJAdviceMethod.invoke(this.aspectInstanceFactory.getAspectInstance(), actualArgs);
    }
    catch (IllegalArgumentException ex) {
        throw new AopInvocationException("Mismatch on arguments to advice method [" +
                this.aspectJAdviceMethod + "]; pointcut expression [" +
                this.pointcut.getPointcutExpression() + "]", ex);
    }
    catch (InvocationTargetException ex) {
        throw ex.getTargetException();
    }
}
```
如上，AspectJMethodBeforeAdvice 的源码比较简单，这里我们仅关注 before 方法。这个方法调用了父类中的 invokeAdviceMethod，然后 invokeAdviceMethod 在调用 invokeAdviceMethodWithGivenArgs，最后在 invokeAdviceMethodWithGivenArgs 通过反射执行通知方法。是不是很简单？

关于 AspectJMethodBeforeAdvice 就简单介绍到这里吧，至于剩下的几种实现，大家可以自己去看看。好了，关于 AspectJMethodBeforeAdvice 的源码分析，就分析到这里了。我们继续往下看吧。

### 2.2 筛选通知器
查找出所有的通知器，整个流程还没算完，接下来我们还要对这些通知器进行筛选。筛选出适合应用在当前 bean 上的通知器。那下面我们来分析一下通知器筛选的过程，如下：
```java
protected List<Advisor> findAdvisorsThatCanApply(
        List<Advisor> candidateAdvisors, Class<?> beanClass, String beanName) {

    ProxyCreationContext.setCurrentProxiedBeanName(beanName);
    try {
        // 调用重载方法
        return AopUtils.findAdvisorsThatCanApply(candidateAdvisors, beanClass);
    }
    finally {
        ProxyCreationContext.setCurrentProxiedBeanName(null);
    }
}

public static List<Advisor> findAdvisorsThatCanApply(List<Advisor> candidateAdvisors, Class<?> clazz) {
    if (candidateAdvisors.isEmpty()) {
        return candidateAdvisors;
    }
    List<Advisor> eligibleAdvisors = new LinkedList<Advisor>();
    for (Advisor candidate : candidateAdvisors) {
        // 筛选 IntroductionAdvisor 类型的通知器
        if (candidate instanceof IntroductionAdvisor && canApply(candidate, clazz)) {
            eligibleAdvisors.add(candidate);
        }
    }
    boolean hasIntroductions = !eligibleAdvisors.isEmpty();
    for (Advisor candidate : candidateAdvisors) {
        if (candidate instanceof IntroductionAdvisor) {
            continue;
        }

        // 筛选普通类型的通知器
        if (canApply(candidate, clazz, hasIntroductions)) {
            eligibleAdvisors.add(candidate);
        }
    }
    return eligibleAdvisors;
}

public static boolean canApply(Advisor advisor, Class<?> targetClass, boolean hasIntroductions) {
    if (advisor instanceof IntroductionAdvisor) {
        /*
         * 从通知器中获取类型过滤器 ClassFilter，并调用 matchers 方法进行匹配。
         * ClassFilter 接口的实现类 AspectJExpressionPointcut 为例，该类的
         * 匹配工作由 AspectJ 表达式解析器负责，具体匹配细节这个就没法分析了，我
         * AspectJ 表达式的工作流程不是很熟
         */
        return ((IntroductionAdvisor) advisor).getClassFilter().matches(targetClass);
    }
    else if (advisor instanceof PointcutAdvisor) {
        PointcutAdvisor pca = (PointcutAdvisor) advisor;
        // 对于普通类型的通知器，这里继续调用重载方法进行筛选
        return canApply(pca.getPointcut(), targetClass, hasIntroductions);
    }
    else {
        return true;
    }
}

public static boolean canApply(Pointcut pc, Class<?> targetClass, boolean hasIntroductions) {
    Assert.notNull(pc, "Pointcut must not be null");
    // 使用 ClassFilter 匹配 class
    if (!pc.getClassFilter().matches(targetClass)) {
        return false;
    }

    MethodMatcher methodMatcher = pc.getMethodMatcher();
    if (methodMatcher == MethodMatcher.TRUE) {
        return true;
    }

    IntroductionAwareMethodMatcher introductionAwareMethodMatcher = null;
    if (methodMatcher instanceof IntroductionAwareMethodMatcher) {
        introductionAwareMethodMatcher = (IntroductionAwareMethodMatcher) methodMatcher;
    }

    /*
     * 查找当前类及其父类（以及父类的父类等等）所实现的接口，由于接口中的方法是 public，
     * 所以当前类可以继承其父类，和父类的父类中所有的接口方法
     */ 
    Set<Class<?>> classes = new LinkedHashSet<Class<?>>(ClassUtils.getAllInterfacesForClassAsSet(targetClass));
    classes.add(targetClass);
    for (Class<?> clazz : classes) {
        // 获取当前类的方法列表，包括从父类中继承的方法
        Method[] methods = ReflectionUtils.getAllDeclaredMethods(clazz);
        for (Method method : methods) {
            // 使用 methodMatcher 匹配方法，匹配成功即可立即返回
            if ((introductionAwareMethodMatcher != null &&
                    introductionAwareMethodMatcher.matches(method, targetClass, hasIntroductions)) ||
                    methodMatcher.matches(method, targetClass)) {
                return true;
            }
        }
    }

    return false;
}
```
以上是通知器筛选的过程，筛选的工作主要由 ClassFilter 和 MethodMatcher 完成。ClassFilter 和 MethodMatcher 两个接口，都有一个 matches 的抽象方法。以 AspectJExpressionPointcut 类型的切点为例。该类型切点实现了ClassFilter 和 MethodMatcher 接口，匹配的工作则是由 AspectJ 表达式解析器负责。除了使用 AspectJ 表达式进行匹配，Spring 还提供了基于正则表达式的切点类，以及更简单的根据方法名进行匹配的切点类。这块内容很多，这里就不展开了。

在完成通知器的查找和筛选过程后，还需要进行最后一步处理 – 对通知器列表进行拓展。怎么拓展呢？我们一起到下一节中一探究竟吧。

### 2.3 拓展筛选出通知器列表
拓展方法 extendAdvisors 做的事情并不多，逻辑也比较简单。我们一起来看一下，如下：
```java
protected void extendAdvisors(List<Advisor> candidateAdvisors) {
    AspectJProxyUtils.makeAdvisorChainAspectJCapableIfNecessary(candidateAdvisors);
}

public static boolean makeAdvisorChainAspectJCapableIfNecessary(List<Advisor> advisors) {
    // 如果通知器列表是一个空列表，则啥都不做
    if (!advisors.isEmpty()) {
        boolean foundAspectJAdvice = false;
        /*
         * 下面的 for 循环用于检测 advisors 列表中是否存在 
         * AspectJ 类型的 Advisor 或 Advice
         */
        for (Advisor advisor : advisors) {
            if (isAspectJAdvice(advisor)) {
                foundAspectJAdvice = true;
            }
        }

        /*
         * 向 advisors 列表的首部添加 DefaultPointcutAdvisor，
         * 至于为什么这样做，我会在后续的文章中进行说明
         */
        if (foundAspectJAdvice && !advisors.contains(ExposeInvocationInterceptor.ADVISOR)) {
            advisors.add(0, ExposeInvocationInterceptor.ADVISOR);
            return true;
        }
    }
    return false;
}

private static boolean isAspectJAdvice(Advisor advisor) {
    return (advisor instanceof InstantiationModelAwarePointcutAdvisor ||
            advisor.getAdvice() instanceof AbstractAspectJAdvice ||
            (advisor instanceof PointcutAdvisor &&
                     ((PointcutAdvisor) advisor).getPointcut() instanceof AspectJExpressionPointcut));
}
```
如上，上面的代码比较少，也不复杂。由源码可以看出 extendAdvisors 是一个空壳方法，除了调用makeAdvisorChainAspectJCapableIfNecessary，该方法没有其他更多的逻辑了。至于 makeAdvisorChainAspectJCapableIfNecessary 这个方法，该方法主要的目的是向通知器列表首部添加 DefaultPointcutAdvisor 类型的通知器，也就是 ExposeInvocationInterceptor.ADVISOR。这种通知器用到的地方不多，了解一下就好。

## 3、总结
本篇文章我们从 AOP 的入口代码出发，看到 AOP 主要分两步：筛选合适的通知器和生成代理对象。筛选合适的通知器是个复杂的工作，因为要考虑两种情况：xml 和注解。对于 xml 形式的通知器，会声明为 Advisor 类型，所以我们的工作是找出所有 Advisor 类型的 beanName 并通过 getBean 的方式获取或创建它；对于注解形式的通知器，我们要找到所有标记了 @Aspect 的 bean，然后把它的每一个标记了 @Before、@After 等表示通知的方法封装成一个通知器。封装的过程分为两步：解析注解里的切点表达式，将其封装成一个 AspectJExpressionPointcut 对象和按照注解类型生成相应的 Advice 实现类。最后封装好的 Advisor 和原有的 Advisor 类型对象会被一起返回。接下来就是筛选工作，筛选是为了找出能和当前 bean 匹配上的 Advisor，这个工作会由 Advisor 中的 Pointcut 对象完成。以 AspectJExpressionPointcut 为例，它实现了 ClassFilter 和 MethodMatcher 两个接口的 matches 方法，内部有一个 AspectJ 表达式解析器，可以判断当前 bean 和 Advisor 是否匹配。然后我们就得到了一组匹配当前 bean 的 Advisor。