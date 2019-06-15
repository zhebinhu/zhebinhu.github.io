---
title: Spring 源码浅析——bean 创建流程
tags: 
	- Spring
	- Java
toc: true
date: 2019-03-04 17:52:47
---
<!--more-->
上一篇中概览了容器刷新的过程，其中着重跟进了容器准备的代码。那么现在容器准备好了，就要创建和往里面注入 bean 了。

## bean 生命周期 

在跟进这部分代码之前，我们首先需要对 Spring 中 bean 的生命周期有个宏观的认识。下面是 bean 生命周期的大致流程：

<img src="./Spring源码浅析——bean 创建流程/bean生命周期.png"/>

接下来对照上图，一步一步对 singleton 类型 bean 的生命周期进行解析：
1. 扫描得到 beanDefinition，里面包含了 bean 创建的全部信息。
2. 调用 BeanFactoryPostProcessor 后置处理方法，可以最后对 beanDefinition 作一些修改。
3. 实例化 bean 对象，类似于 new XXObject()。
4. 将配置文件或者注解中设置的属性填充到刚刚创建的 bean 对象中。
5. 检查 bean 对象是否实现了 Aware 一类的接口，如果实现了则把相应的依赖设置到 bean 对象中。比如如果 bean 实现了 BeanFactoryAware 接口，Spring 容器在实例化bean的过程中，会将 BeanFactory 容器注入到 bean 中。
6. 调用 BeanPostProcessor 前置处理方法，即 postProcessBeforeInitialization(Object bean, String beanName)。
7. 检查 bean 对象是否实现了 InitializingBean 接口，如果实现，则调用 afterPropertiesSet 方法。或者检查配置文件中是否配置了 init-method 属性，如果配置了，则去调用 init-method 属性配置的方法。
8. 调用 BeanPostProcessor 后置处理方法，即 postProcessAfterInitialization(Object bean, String beanName)。我们所熟知的 AOP 就是在这里将 Advice 逻辑织入到 bean 中的。
9. 注册 Destruction 相关回调方法。
10. bean 对象处于就绪状态，可以使用了。
11. 应用上下文被销毁，调用注册的 Destruction 相关方法。如果 bean 实现了 DispostbleBean 接口，Spring 容器会调用 destroy 方法。如果在配置文件中配置了 destroy 属性，Spring 容器则会调用 destroy 属性对应的方法。

## beanDefinition 介绍

我们走完了容器准备流程，其实就已经走到了第三步。此时 `beanDefinition` 已经保存在我们的容器中了。beanDefinition 对象顾名思义保存的就是 bean 的定义信息。它用 Java 类的方式保存了我们在 xml 或者注解中对 bean 对象的配置。然后 Spring 就根据它里面保存的信息初始化 bean 对象。BeanDefinition 的接口定义如下：

```java
public interface BeanDefinition extends AttributeAccessor, BeanMetadataElement {
   // 我们可以看到，默认只提供 sington 和 prototype 两种，
   // 大家可能知道还有 request, session, globalSession, application, websocket 这几种，
   // 不过，它们属于基于 web 的扩展。
   String SCOPE_SINGLETON = ConfigurableBeanFactory.SCOPE_SINGLETON;
   String SCOPE_PROTOTYPE = ConfigurableBeanFactory.SCOPE_PROTOTYPE;

   // 比较不重要，直接跳过吧
   int ROLE_APPLICATION = 0;
   int ROLE_SUPPORT = 1;
   int ROLE_INFRASTRUCTURE = 2;

   // 设置父 bean，这里涉及到 bean 继承，不是 java 继承。一句话就是：继承父 bean 的配置信息
   void setParentName(String parentName);
   String getParentName();

   // 设置 bean 的类名称，将来是要通过反射来生成实例的
   void setBeanClassName(String beanClassName);
   String getBeanClassName();

   // 设置 bean 的 scope
   void setScope(String scope);
   String getScope();

   // 设置是否懒加载
   void setLazyInit(boolean lazyInit);
   boolean isLazyInit();

   // 设置该 bean 依赖的所有的 bean，注意，这里的依赖不是指属性依赖(如 @Autowire 标记的)，
   // 是 depends-on="" 属性设置的值。一句话就是：不直接依赖于其它 bean 但希望其它 bean 先初始化
   void setDependsOn(String... dependsOn);
   String[] getDependsOn();

   // 设置该 bean 是否可以注入到其他 bean 中，只对根据类型注入有效，
   // 如果根据名称注入，即使这边设置了 false，也是可以的
   void setAutowireCandidate(boolean autowireCandidate);
   boolean isAutowireCandidate();

   // 设置是否 primary。同一接口的如果有多个实现，如果不指定名字的话，Spring 会优先选择设置 primary 为 true 的 bean
   void setPrimary(boolean primary);
   boolean isPrimary();

   // 如果该 Bean 采用工厂方法生成，指定工厂名称。
   // 一句话就是：有些实例不是用反射生成的，而是用工厂模式生成的
   void setFactoryBeanName(String factoryBeanName);
   // 获取工厂名称
   String getFactoryBeanName();
   // 指定工厂类中的 工厂方法名称
   void setFactoryMethodName(String factoryMethodName);
   // 获取工厂类中的 工厂方法名称
   String getFactoryMethodName();

   // 构造器参数
   ConstructorArgumentValues getConstructorArgumentValues();

   // Bean 中的属性值，后面给 bean 注入属性值的时候会说到
   MutablePropertyValues getPropertyValues();

   // 是否 singleton
   boolean isSingleton();

   // 是否 prototype
   boolean isPrototype();

   // 如果这个 Bean 是被设置为 abstract，那么不能实例化，
   // 常用于作为父 bean 用于继承，其实也很少用......
   boolean isAbstract();

   int getRole();
   String getDescription();
   String getResourceDescription();
   BeanDefinition getOriginatingBeanDefinition();
}
```
了解了 beanDefinition 之后，接下来我们就要看 Spring 是如何把这个定义信息转化成具体的对象的。

## 源码分析

我们来总结一下，到目前为止，应该说 BeanFactory 已经创建完成，并且所有的实现了 BeanFactoryPostProcessor 接口的 bean 都已经初始化并且其中的 postProcessBeanFactory(factory) 方法已经得到回调执行了。而且 Spring 已经“手动”注册了一些特殊的 bean，如 `environment`、`systemProperties`  等。

剩下的就是初始化 singleton beans 了，我们知道它们是单例的，如果没有设置懒加载，那么 Spring 会在接下来初始化所有的 singleton beans。进入上篇略过的 `finishBeanFactoryInitialization` 方法。
### 1、finishBeanFactoryInitialization
// AbstractApplicationContext 835
```java
// 初始化剩余的 singleton beans
protected void finishBeanFactoryInitialization(ConfigurableListableBeanFactory beanFactory) {
   // 首先，初始化名字为 conversionService 的 Bean。
   // conversionService 用的很多。它是容器级的全局类型转换器，常见的有 String 转 Date 的类型转换器等
   // 什么，看代码这里没有初始化 Bean 啊！
   // 注意了，初始化的动作包装在 beanFactory.getBean(...) 中，这里先不说细节，先往下看吧
   if (beanFactory.containsBean(CONVERSION_SERVICE_BEAN_NAME) &&
         beanFactory.isTypeMatch(CONVERSION_SERVICE_BEAN_NAME, ConversionService.class)) {
      beanFactory.setConversionService(
            beanFactory.getBean(CONVERSION_SERVICE_BEAN_NAME, ConversionService.class));
   }
   // 检查 beanFactory 是否没有内嵌值解析器，默认是有的
   if (!beanFactory.hasEmbeddedValueResolver()) {
      beanFactory.addEmbeddedValueResolver(new StringValueResolver() {
         @Override
         public String resolveStringValue(String strVal) {
            return getEnvironment().resolvePlaceholders(strVal);
         }
      });
   }
   // 加载第三方模块，如 AspectJ；这个不重要，跳过
   String[] weaverAwareNames = beanFactory.getBeanNamesForType(LoadTimeWeaverAware.class, false, false);
   for (String weaverAwareName : weaverAwareNames) {
      getBean(weaverAwareName);
   }
   // 停用临时类加载器
   beanFactory.setTempClassLoader(null);
   // 禁止对 bean 的定义再修改。
   // 没什么别的目的，因为到这一步的时候，Spring 已经开始预初始化 singleton beans 了，
   // 肯定不希望这个时候还出现 bean 定义解析、加载、注册。
   beanFactory.freezeConfiguration();
   // 开始初始化
   beanFactory.preInstantiateSingletons();
}
```
从上面最后一行往里看，默认 beanFactory 的实现类就是 DefaultListableBeanFactory 这个类了，我们进入它的 `preInstantiateSingletons` 方法来看一看。
### 2、preInstantiateSingletons
// DefaultListableBeanFactory 728
```java
public void preInstantiateSingletons() throws BeansException {
    // this.beanDefinitionNames 保存了所有的 beanNames
    List<String> beanNames = new ArrayList<>(this.beanDefinitionNames);
    // 触发所有的非懒加载的 singleton beans 的初始化操作
    for (String beanName : beanNames) {
        // 合并父 beanDefinition 与子 beanDefinition，涉及到 bean 继承的关系，前面提到过：子 bean 继承父 bean 的配置信息
        // 详情可见附录
        RootBeanDefinition bd = getMergedLocalBeanDefinition(beanName);
        // 非抽象、非懒加载的 singletons。如果配置了 'abstract = true'，那是不需要初始化的
        if (!bd.isAbstract() && bd.isSingleton() && !bd.isLazyInit()) {
            // 处理 FactoryBean（如果不熟悉，附录中有介绍）
            if (isFactoryBean(beanName)) {
                // FactoryBean 的话，在 beanName 前面加上 ‘&’ 符号。再调用 getBean
                Object bean = getBean(FACTORY_BEAN_PREFIX + beanName);
                if (bean instanceof FactoryBean) {
                    final FactoryBean<?> factory = (FactoryBean<?>) bean;
                    boolean isEagerInit;
                    // 这里需要判断是不是 SmartFactoryBean，
                    // 因为 SmartFactoryBean 会定义一个 isEagerInit() 方法来决定 getObject() 的实例对象是否懒加载
                    if (System.getSecurityManager() != null && factory instanceof SmartFactoryBean) {
                        isEagerInit = AccessController.doPrivileged((PrivilegedAction<Boolean>)
                                        ((SmartFactoryBean<?>) factory)::isEagerInit,
                                getAccessControlContext());
                    }
                    else {
                        isEagerInit = (factory instanceof SmartFactoryBean &&
                                ((SmartFactoryBean<?>) factory).isEagerInit());
                    }
                    // 对非懒加载的 bean 实例化
                    if (isEagerInit) {
                        getBean(beanName);
                    }
                }
            }
           // 对于普通的 Bean，只要调用 getBean(beanName) 这个方法就可以进行初始化了
            else {
                getBean(beanName);
            }
        }
    }
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
接下来，我们就进入到 `getBean(beanName)` 方法了，这个方法我们经常用来从 BeanFactory 中获取一个 Bean，而初始化的过程也封装到了这个方法里。

### 3、getBean
// AbstractBeanFactory 198
```java
@Override
public Object getBean(String name) throws BeansException {
    return doGetBean(name, null, null, false);
}

// getBean 方法是我们经常用来获取 bean 的，但它也同时封装了初始化的过程，已经初始化过了就从容器中直接返回，否则就先初始化再返回
protected <T> T doGetBean(final String name, @Nullable final Class<T> requiredType,
                          @Nullable final Object[] args, boolean typeCheckOnly) throws BeansException {

    // 获取一个 “正统的” beanName，处理两种情况，一个是前面说的 FactoryBean(前面带 ‘&’)，
    // 一个是别名问题，因为这个方法是 getBean，获取 Bean 用的，你要是传一个别名进来，是完全可以的
    final String beanName = transformedBeanName(name);
    // 这个是返回值
    Object bean;

    // 检查下是不是已经创建过了
    Object sharedInstance = getSingleton(beanName);
     // if 内部是获取 bean 的逻辑。
     // 这里说下 args，前面我们一路进来的时候都是 getBean(beanName)，所以 args 传参其实是 null 的，
     // 但是如果 args 不为空的时候，那么意味着调用方不是希望获取 Bean，而是创建 Bean 
    if (sharedInstance != null && args == null) {
        if (logger.isTraceEnabled()) {
            if (isSingletonCurrentlyInCreation(beanName)) {
                logger.trace("Returning eagerly cached instance of singleton bean '" + beanName +
                        "' that is not fully initialized yet - a consequence of a circular reference");
            }
            else {
                logger.trace("Returning cached instance of singleton bean '" + beanName + "'");
            }
        }
        // 下面这个方法，如果是普通 Bean 的话，直接返回 sharedInstance，如果是 FactoryBean 的话，返回它创建的那个实例对象。
        // 如果对 FactoryBean 不熟悉，附录中有介绍。
        bean = getObjectForBeanInstance(sharedInstance, name, beanName, null);
    } 
    // else 内部是初始化 bean 的逻辑
    else {
        // 当前 beanName 的 prototype 类型的 bean 正在被创建则抛异常
        // 往往是因为陷入了循环引用。prototype 类型的 bean 的循环引用是没法被解决的。这跟 Java 里面的一样，会导致栈溢出。
        if (isPrototypeCurrentlyInCreation(beanName)) {
            throw new BeanCurrentlyInCreationException(beanName);
        }

        BeanFactory parentBeanFactory = getParentBeanFactory();
        // 检查一下这个 BeanDefinition 在容器中是否存在
        if (parentBeanFactory != null && !containsBeanDefinition(beanName)) {
            // 如果当前容器不存在这个 BeanDefinition，试试父容器中有没有
            String nameToLookup = originalBeanName(name);
            // 返回父容器的查询结果 
            if (parentBeanFactory instanceof AbstractBeanFactory) {
                // Delegation to parent with explicit args.
                return ((AbstractBeanFactory) parentBeanFactory).doGetBean(
                        nameToLookup, requiredType, args, typeCheckOnly);
            }
            else if (args != null) {
                // Delegation to parent with explicit args.
                return (T) parentBeanFactory.getBean(nameToLookup, args);
            }
            else if (requiredType != null) {
                // No args -> delegate to standard getBean method.
                return parentBeanFactory.getBean(nameToLookup, requiredType);
            }
            else {
                return (T) parentBeanFactory.getBean(nameToLookup);
            }
        }
        // typeCheckOnly 为 false，将当前 beanName 放入一个 alreadyCreated 的 Set 集合中
        if (!typeCheckOnly) {
            markBeanAsCreated(beanName);
        }
       /**
        * 稍稍总结一下：
        * 到这里的话，要准备创建 Bean 了，对于 singleton 的 Bean 来说，容器中还没创建过此 Bean；
        * 对于 prototype 的 Bean 来说，本来就是要创建一个新的 Bean。
        */
        try {
            final RootBeanDefinition mbd = getMergedLocalBeanDefinition(beanName);
            checkMergedBeanDefinition(mbd, beanName, args);

            // 先初始化依赖的所有 Bean，注意，这里的依赖指的是 depends-on 中定义的依赖
            String[] dependsOn = mbd.getDependsOn();
            if (dependsOn != null) {
                for (String dep : dependsOn) {
                    // 检查是不是有循环依赖
                    // 这里的依赖还是 depends-on 中定义的依赖
                    if (isDependent(beanName, dep)) {
                        throw new BeanCreationException(mbd.getResourceDescription(), beanName,
                                "Circular depends-on relationship between '" + beanName + "' and '" + dep + "'");
                    }
                    // 注册一下依赖关系
                    registerDependentBean(dep, beanName);
                    try {
                        // 先初始化被依赖项
                        getBean(dep);
                    }
                    catch (NoSuchBeanDefinitionException ex) {
                        throw new BeanCreationException(mbd.getResourceDescription(), beanName,
                                "'" + beanName + "' depends on missing bean '" + dep + "'", ex);
                    }
                }
            }

            // 如果是 singleton scope 的，创建 singleton 的实例
            if (mbd.isSingleton()) {
                 // 这里并没有直接调用 createBean 方法创建 bean 实例，而是通过 getSingleton(String, ObjectFactory) 方法获取 bean 实例。  
                 // getSingleton(String, ObjectFactory) 方法会在内部调用 ObjectFactory 的 getObject() 方法创建 bean，并会在创建完成后，
                 // 将 bean 放入缓存中。
                sharedInstance = getSingleton(beanName, () -> {
                    try {
                        // 执行创建 Bean，详情后面再说
                        return createBean(beanName, mbd, args);
                    }
                    catch (BeansException ex) {
                        destroySingleton(beanName);
                        throw ex;
                    }
                });
                // 跟上面的一样，如果是普通 Bean 的话，直接返回 sharedInstance，如果是 FactoryBean 的话，返回它创建的那个实例对象。
                bean = getObjectForBeanInstance(sharedInstance, name, beanName, mbd);
            }

            // 如果是 prototype scope 的，创建 prototype 的实例
            else if (mbd.isPrototype()) {
                // prototype 对象每次获取都会创建新的实例
                Object prototypeInstance = null;
                try {
                    beforePrototypeCreation(beanName);
                    // 执行创建 Bean
                    prototypeInstance = createBean(beanName, mbd, args);
                }
                finally {
                    afterPrototypeCreation(beanName);
                }
                bean = getObjectForBeanInstance(prototypeInstance, name, beanName, mbd);
            }

            // 如果不是 singleton 和 prototype 的话，需要委托给相应的实现类来处理
            else {
                String scopeName = mbd.getScope();
                final Scope scope = this.scopes.get(scopeName);
                if (scope == null) {
                    throw new IllegalStateException("No Scope registered for scope name '" + scopeName + "'");
                }
                try {
                    Object scopedInstance = scope.get(beanName, () -> {
                        beforePrototypeCreation(beanName);
                        try {
                            // 执行创建 Bean
                            return createBean(beanName, mbd, args);
                        }
                        finally {
                            afterPrototypeCreation(beanName);
                        }
                    });
                    bean = getObjectForBeanInstance(scopedInstance, name, beanName, mbd);
                }
                catch (IllegalStateException ex) {
                    throw new BeanCreationException(beanName,
                            "Scope '" + scopeName + "' is not active for the current thread; consider " +
                                    "defining a scoped proxy for this bean if you intend to refer to it from a singleton",
                            ex);
                }
            }
        }
        catch (BeansException ex) {
            cleanupAfterBeanCreationFailure(beanName);
            throw ex;
        }
    }

    // 最后，检查一下类型对不对，不对的话就抛异常，对的话就返回了
    if (requiredType != null && !requiredType.isInstance(bean)) {
        try {
            T convertedBean = getTypeConverter().convertIfNecessary(bean, requiredType);
            if (convertedBean == null) {
                throw new BeanNotOfRequiredTypeException(name, requiredType, bean.getClass());
            }
            return convertedBean;
        }
        catch (TypeMismatchException ex) {
            if (logger.isTraceEnabled()) {
                logger.trace("Failed to convert bean '" + name + "' to required type '" +
                        ClassUtils.getQualifiedName(requiredType) + "'", ex);
            }
            throw new BeanNotOfRequiredTypeException(name, requiredType, bean.getClass());
        }
    }
    return (T) bean;
}
```
到了这儿，我们会发现当 Spring 获取不到 bean 的时候，会调用 `createBean` 方法进行创建。singleton 和 prototype 对象的区别在于是否通过 `getSingleton` 这个方法调用，我们来看看 getSingleton 方法是如何运作的。

### 4、getSingleton
// DefaultSingletonBeanRegistry 202
```java
public Object getSingleton(String beanName, ObjectFactory<?> singletonFactory) {
    Assert.notNull(beanName, "Bean name must not be null");
    synchronized (this.singletonObjects) {
        // 从 singletonObjects 获取实例，singletonObjects 中缓存的实例都是完全实例化好的 bean，可以直接使用
        Object singletonObject = this.singletonObjects.get(beanName);
        // 如果 singletonObject = null，表明还没创建，或者还没完全创建好。
        if (singletonObject == null) {
            if (this.singletonsCurrentlyInDestruction) {
                throw new BeanCreationNotAllowedException(beanName,
                        "Singleton bean creation not allowed while singletons of this factory are in destruction " +
                                "(Do not request a bean from a BeanFactory in a destroy method implementation!)");
            }
            if (logger.isDebugEnabled()) {
                logger.debug("Creating shared instance of singleton bean '" + beanName + "'");
            }
            beforeSingletonCreation(beanName);
            boolean newSingleton = false;
            boolean recordSuppressedExceptions = (this.suppressedExceptions == null);
            if (recordSuppressedExceptions) {
                this.suppressedExceptions = new LinkedHashSet<>();
            }
            try {
                // 调用 singletonFactory 的 getObject 方法，就是传入的匿名类，最终也是调用 createBean
                singletonObject = singletonFactory.getObject();
                newSingleton = true;
            }
            catch (IllegalStateException ex) {
                singletonObject = this.singletonObjects.get(beanName);
                if (singletonObject == null) {
                    throw ex;
                }
            }
            catch (BeanCreationException ex) {
                if (recordSuppressedExceptions) {
                    for (Exception suppressedException : this.suppressedExceptions) {
                        ex.addRelatedCause(suppressedException);
                    }
                }
                throw ex;
            }
            finally {
                if (recordSuppressedExceptions) {
                    this.suppressedExceptions = null;
                }
                afterSingletonCreation(beanName);
            }
            if (newSingleton) {
                // 将创建好的 bean 存入缓存
                addSingleton(beanName, singletonObject);
            }
        }
        return singletonObject;
    }
}
```
我们可以看到 getSingleton 内部也是调用 createBean 方法，只是在调用之前会先去缓存中找，调用之后会把创建好的 bean 存入缓存中。下面就到了重头戏 `createBean` 方法了。

### 5、createBean
// AbstractAutowireCapableBeanFactory 447
```java
@Override
protected Object createBean(String beanName, RootBeanDefinition mbd, @Nullable Object[] args)
        throws BeanCreationException {

    if (logger.isTraceEnabled()) {
        logger.trace("Creating instance of bean '" + beanName + "'");
    }
    RootBeanDefinition mbdToUse = mbd;

    // 确保 BeanDefinition 中的 Class 被加载
    Class<?> resolvedClass = resolveBeanClass(mbd, beanName);
    if (resolvedClass != null && !mbd.hasBeanClass() && mbd.getBeanClassName() != null) {
        mbdToUse = new RootBeanDefinition(mbd);
        mbdToUse.setBeanClass(resolvedClass);
    }

    // 涉及到一个概念：方法覆写。具体涉及到 lookup-method 和 replace-method 两个标签，附录中会有介绍   
    try {
        mbdToUse.prepareMethodOverrides();
    }
    catch (BeanDefinitionValidationException ex) {
        throw new BeanDefinitionStoreException(mbdToUse.getResourceDescription(),
                beanName, "Validation of method overrides failed", ex);
    }

    try {
       // 让 InstantiationAwareBeanPostProcessor 在这一步有机会返回代理，在 AOP 相关文章会有解释，这里先跳过
        Object bean = resolveBeforeInstantiation(beanName, mbdToUse);
        if (bean != null) {
            return bean;
        }
    }
    catch (Throwable ex) {
        throw new BeanCreationException(mbdToUse.getResourceDescription(), beanName,
                "BeanPostProcessor before instantiation of bean failed", ex);
    }

    try {
        // 重头戏，创建 bean
        Object beanInstance = doCreateBean(beanName, mbdToUse, args);
        if (logger.isTraceEnabled()) {
            logger.trace("Finished creating instance of bean '" + beanName + "'");
        }
        return beanInstance;
    }
    catch (BeanCreationException | ImplicitlyAppearedSingletonException ex) {
        throw ex;
    }
    catch (Throwable ex) {
        throw new BeanCreationException(
                mbdToUse.getResourceDescription(), beanName, "Unexpected exception during bean creation", ex);
    }
}
```
createBean 并不是真正初始化 bean 的方法，而是对 `doCreateBean` 的预处理。它主要做了两件事情：确保 BeanDefinition 中的 Class 被加载和准备方法覆写。真正创建 bean 对象的逻辑在 doCreateBean 方法里面。

这里我们稍微总结一下。目前为止，我们已经到了真正创建 bean 对象的 `doCreateBean` 这个方法。而在这之前，从容器创建到开始执行真正的创建，我们也经历了相当多的步骤。主要有：
1. 触发初始化操作
2. 合并父 beanDefinition 与子 beanDefinition
3. 过滤掉抽象、懒加载的、非单例的 bean
4. 预处理 FactoryBean（加'&'，懒加载判断）
5. 别名转化
6. 尝试从缓存中获取
7. 检查 BeanDefinition 是否存在，不存在就去父容器创建
8. 先初始化 depends-on 中定义的依赖
9. 准备方法覆写
10. 创建并缓存 bean
11. 对 FactoryBean 额外处理
12. 返回 bean

这些步骤确保了 bean 可以被创建且能按用户定义的方式创建。下面我们将详细分析真正创建 bean 对象的 `doCreateBean` 方法内部的逻辑。

### 6、doCreateBean
// AbstractAutowireCapableBeanFactory 529
```java
protected Object doCreateBean(final String beanName, final RootBeanDefinition mbd, final @Nullable Object[] args)
        throws BeanCreationException { 
     
    // BeanWrapper 是一个基础接口，由接口名可看出这个接口的实现类用于包裹 bean 实例。
    // 通过 BeanWrapper 的实现类可以方便的设置/获取 bean 实例的属性
    BeanWrapper instanceWrapper = null;
    if (mbd.isSingleton()) {
        // 从缓存中获取 BeanWrapper，并清理相关记录
        instanceWrapper = this.factoryBeanInstanceCache.remove(beanName);
    }
    if (instanceWrapper == null) {
        // 创建 bean 实例，并将实例包裹在 BeanWrapper 实现类对象中返回，之后会细谈
        instanceWrapper = createBeanInstance(beanName, mbd, args);
    }
    // 此处的 bean 可以认为是一个原始的 bean 实例，暂未填充属性
    final Object bean = instanceWrapper.getWrappedInstance();
    Class<?> beanType = instanceWrapper.getWrappedClass();
    if (beanType != NullBean.class) {
        mbd.resolvedTargetType = beanType;
    }

    // 涉及接口：MergedBeanDefinitionPostProcessor，用于处理已“合并的 BeanDefinition”，这块细节就不展开了
    synchronized (mbd.postProcessingLock) {
        if (!mbd.postProcessed) {
            try {
                applyMergedBeanDefinitionPostProcessors(mbd, beanType, beanName);
            }
            catch (Throwable ex) {
                throw new BeanCreationException(mbd.getResourceDescription(), beanName,
                        "Post-processing of merged bean definition failed", ex);
            }
            mbd.postProcessed = true;
        }
    }

    // earlySingletonExposure 是一个重要的变量，用于解决循环依赖，该变量表示是否提前暴露，
    // earlySingletonExposure = 单例 && 是否允许循环依赖 && 是否存于创建状态中
    boolean earlySingletonExposure = (mbd.isSingleton() && this.allowCircularReferences &&
            isSingletonCurrentlyInCreation(beanName));
    if (earlySingletonExposure) {
        if (logger.isTraceEnabled()) {
            logger.trace("Eagerly caching bean '" + beanName +
                    "' to allow for resolving potential circular references");
        }
        // 添加工厂对象到 singletonFactories 缓存中
        addSingletonFactory(beanName, new ObjectFactory<Object>() {
            @Override
            public Object getObject() throws BeansException {
                // 获取早期 bean 的引用，如果 bean 中的方法被 AOP 切点所匹配到，此时 AOP 相关逻辑会介入
                return getEarlyBeanReference(beanName, mbd, bean);
            }
        });
    }

    Object exposedObject = bean;
    try {
        // 这一步也是非常关键的，这一步负责属性装配，因为前面的实例只是实例化了，并没有设值，这里就是设值
        populateBean(beanName, mbd, instanceWrapper);
        // 进行余下的初始化工作，之后会细谈
        exposedObject = initializeBean(beanName, exposedObject, mbd);
    }
    catch (Throwable ex) {
        if (ex instanceof BeanCreationException && beanName.equals(((BeanCreationException) ex).getBeanName())) {
            throw (BeanCreationException) ex;
        }
        else {
            throw new BeanCreationException(
                    mbd.getResourceDescription(), beanName, "Initialization of bean failed", ex);
        }
    }

    if (earlySingletonExposure) {
        Object earlySingletonReference = getSingleton(beanName, false);
        if (earlySingletonReference != null) {
            if (exposedObject == bean) {
                exposedObject = earlySingletonReference;
            }
            else if (!this.allowRawInjectionDespiteWrapping && hasDependentBean(beanName)) {
                String[] dependentBeans = getDependentBeans(beanName);
                Set<String> actualDependentBeans = new LinkedHashSet<>(dependentBeans.length);
                for (String dependentBean : dependentBeans) {
                    if (!removeSingletonIfCreatedForTypeCheckOnly(dependentBean)) {
                        actualDependentBeans.add(dependentBean);
                    }
                }
                if (!actualDependentBeans.isEmpty()) {
                    throw new BeanCurrentlyInCreationException(beanName,
                            "Bean with name '" + beanName + "' has been injected into other beans [" +
                                    StringUtils.collectionToCommaDelimitedString(actualDependentBeans) +
                                    "] in its raw version as part of a circular reference, but has eventually been " +
                                    "wrapped. This means that said other beans do not use the final version of the " +
                                    "bean. This is often the result of over-eager type matching - consider using " +
                                    "'getBeanNamesOfType' with the 'allowEagerInit' flag turned off, for example.");
                }
            }
        }
    }

    // 注册销毁逻辑
    try {
        registerDisposableBeanIfNecessary(beanName, bean, mbd);
    }
    catch (BeanDefinitionValidationException ex) {
        throw new BeanCreationException(
                mbd.getResourceDescription(), beanName, "Invalid destruction signature", ex);
    }

    return exposedObject;
}
```
我们看到 doCreateBean 内部的逻辑非常多，我们先来总结一下 doCreateBean 方法的执行流程吧，如下：
1. 从缓存中获取 BeanWrapper 实现类对象，并清理相关记录
2. 若未命中缓存，则创建 bean 实例，并将实例包裹在 BeanWrapper 实现类对象中返回
3. 应用 MergedBeanDefinitionPostProcessor 后置处理器相关逻辑
4. 根据条件决定是否提前暴露 bean 的早期引用（early reference），用于处理循环依赖问题
5. 调用 populateBean 方法向 bean 实例中填充属性
6. 调用 initializeBean 方法完成余下的初始化工作
7. 注册销毁逻辑

接下来我们挑 doCreateBean 中的三个细节出来说说。一个是创建 Bean 实例的 `createBeanInstance` 方法，一个是依赖注入的 `populateBean` 方法，还有就是回调方法 `initializeBean`。

#### 6.1、创建实例
// AbstractAutowireCapableBeanFactory 1112
```java
protected BeanWrapper createBeanInstance(String beanName, RootBeanDefinition mbd, @Nullable Object[] args) {
    // 确保已经加载了此 class
    Class<?> beanClass = resolveBeanClass(mbd, beanName);
    
    // 校验一下这个类的访问权限
    if (beanClass != null && !Modifier.isPublic(beanClass.getModifiers()) && !mbd.isNonPublicAccessAllowed()) {
        throw new BeanCreationException(mbd.getResourceDescription(), beanName,
                "Bean class isn't public, and non-public access not allowed: " + beanClass.getName());
    }

    Supplier<?> instanceSupplier = mbd.getInstanceSupplier();
    if (instanceSupplier != null) {
        return obtainFromSupplier(instanceSupplier, beanName);
    }

    // 如果工厂方法不为空，则通过工厂方法构建 bean 对象。工厂方式可以见附录
    if (mbd.getFactoryMethodName() != null) {
        return instantiateUsingFactoryMethod(beanName, mbd, args);
    }

    // 如果不是第一次创建，比如第二次创建 prototype bean。这种情况下，我们可以从第一次创建知道，
    // 采用无参构造函数，还是构造函数依赖注入来完成实例化。
    // 这里的 resolved 和 mbd.constructorArgumentsResolved 将会在 bean 第一次实例化的过程中被设置，在后面的源码中会分析到，先继续往下看。
    boolean resolved = false;
    boolean autowireNecessary = false;
    if (args == null) {
        synchronized (mbd.constructorArgumentLock) {
            if (mbd.resolvedConstructorOrFactoryMethod != null) {
                resolved = true;
                autowireNecessary = mbd.constructorArgumentsResolved;
            }
        }
    }
    if (resolved) {
        if (autowireNecessary) {
            // 通过有参构造器构造 bean 对象
            return autowireConstructor(beanName, mbd, null, null);
        }
        else {
            // 通过无参构造器构造 bean 对象
            return instantiateBean(beanName, mbd);
        }
    }

    // 判断是否采用有参构造函数
    Constructor<?>[] ctors = determineConstructorsFromBeanPostProcessors(beanClass, beanName);
    if (ctors != null || mbd.getResolvedAutowireMode() == AUTOWIRE_CONSTRUCTOR ||
            mbd.hasConstructorArgumentValues() || !ObjectUtils.isEmpty(args)) {
        // 通过有参构造器构造 bean 对象
        return autowireConstructor(beanName, mbd, ctors, args);
    }

    // 通过无参构造器构造 bean 对象
    return instantiateBean(beanName, mbd);
}
```
以上就是 createBeanInstance 方法的源码，不是很长。配合着注释，应该不是很难懂。下面我们来总结一下这个方法的执行流程，如下：
1. 检测类的访问权限，若禁止访问，则抛出异常
2. 若工厂方法不为空，则通过工厂方法构建 bean 对象，并返回结果
3. 若构造方式已解析过，则走快捷路径构建 bean 对象，并返回结果
4. 如第三步不满足，则通过组合条件决定使用哪种方式构建 bean 对象

工厂方法就不深入了，下面我们来看看使用`有参构造器方式`和`无参构造器方式`创建 bean 的过程。
##### 6.1.1、有参构造器方式
// AbstractAutowireCapableBeanFactory 1305
```java
protected BeanWrapper autowireConstructor(
    String beanName, RootBeanDefinition mbd, Constructor<?>[] ctors, Object[] explicitArgs) {
    // 创建 ConstructorResolver 对象，并调用其 autowireConstructor 方法
    return new ConstructorResolver(this).autowireConstructor(beanName, mbd, ctors, explicitArgs);
}

public BeanWrapper autowireConstructor(String beanName, RootBeanDefinition mbd,
        @Nullable Constructor<?>[] chosenCtors, @Nullable Object[] explicitArgs) {

    // 创建 BeanWrapperImpl 对象
    BeanWrapperImpl bw = new BeanWrapperImpl();
    this.beanFactory.initBeanWrapper(bw);

    Constructor<?> constructorToUse = null;
    ArgumentsHolder argsHolderToUse = null;
    Object[] argsToUse = null;

    // 确定参数值列表（argsToUse）
    if (explicitArgs != null) {
        argsToUse = explicitArgs;
    }
    else {
        Object[] argsToResolve = null;
        synchronized (mbd.constructorArgumentLock) {
            // 获取已解析的构造方法
            constructorToUse = (Constructor<?>) mbd.resolvedConstructorOrFactoryMethod;
            if (constructorToUse != null && mbd.constructorArgumentsResolved) {
                // 获取已解析的构造方法参数列表
                argsToUse = mbd.resolvedConstructorArguments;
                if (argsToUse == null) {
                    // 若 argsToUse 为空，则获取未解析的构造方法参数列表
                    argsToResolve = mbd.preparedConstructorArguments;
                }
            }
        }
        if (argsToResolve != null) {
            // 解析参数列表
            argsToUse = resolvePreparedArguments(beanName, mbd, bw, constructorToUse, argsToResolve);
        }
    }

    if (constructorToUse == null) {
        boolean autowiring = (chosenCtors != null ||
                mbd.getResolvedAutowireMode() == RootBeanDefinition.AUTOWIRE_CONSTRUCTOR);
        ConstructorArgumentValues resolvedValues = null;

        int minNrOfArgs;
        if (explicitArgs != null) {
            minNrOfArgs = explicitArgs.length;
        }
        else {
            ConstructorArgumentValues cargs = mbd.getConstructorArgumentValues();
            resolvedValues = new ConstructorArgumentValues();
            /*
             * 确定构造方法参数数量，比如下面的配置：
             *     <bean id="persion" class="com.huzb.demo.Person">
             *         <constructor-arg index="0" value="xiaoming"/>
             *         <constructor-arg index="1" value="1"/>
             *         <constructor-arg index="2" value="man"/>
             *     </bean>
             *
             * 此时 minNrOfArgs = maxIndex + 1 = 2 + 1 = 3，除了计算 minNrOfArgs，
             * 下面的方法还会将 cargs 中的参数数据转存到 resolvedValues 中
             */
            minNrOfArgs = resolveConstructorArguments(beanName, mbd, bw, cargs, resolvedValues);
        }

        // 获取构造方法列表
        Constructor<?>[] candidates = chosenCtors;
        if (candidates == null) {
            Class<?> beanClass = mbd.getBeanClass();
            try {
                candidates = (mbd.isNonPublicAccessAllowed() ?
                        beanClass.getDeclaredConstructors() : beanClass.getConstructors());
            }
            catch (Throwable ex) {
                throw new BeanCreationException(mbd.getResourceDescription(), beanName,
                        "Resolution of declared constructors on bean Class [" + beanClass.getName() +
                        "] from ClassLoader [" + beanClass.getClassLoader() + "] failed", ex);
            }
        }

        // 按照构造方法的访问权限级别和参数数量进行排序
        AutowireUtils.sortConstructors(candidates);

        int minTypeDiffWeight = Integer.MAX_VALUE;
        Set<Constructor<?>> ambiguousConstructors = null;
        LinkedList<UnsatisfiedDependencyException> causes = null;

        for (Constructor<?> candidate : candidates) {
            Class<?>[] paramTypes = candidate.getParameterTypes();

            /*
             * 下面的 if 分支的用途是：若匹配到到合适的构造方法了，提前结束 for 循环
             * constructorToUse != null 这个条件比较好理解，下面分析一下条件 argsToUse.length > paramTypes.length：
             * 前面说到 AutowireUtils.sortConstructors(candidates) 用于对构造方法进行排序，排序规则如下：
             *   1. 具有 public 访问权限的构造方法排在非 public 构造方法前
             *   2. 参数数量多的构造方法排在前面
             *
             * 假设现在有一组构造方法按照上面的排序规则进行排序，排序结果如下（省略参数名称）：
             *
             *   1. public Hello(Object, Object, Object)
             *   2. public Hello(Object, Object)
             *   3. public Hello(Object)
             *   4. protected Hello(Integer, Object, Object, Object)
             *   5. protected Hello(Integer, Object, Object)
             *   6. protected Hello(Integer, Object)
             *
             * argsToUse = [num1, obj2]，可以匹配上的构造方法2和构造方法6。由于构造方法2有更高的访问权限，
             * 所以没理由不选他（尽管后者在参数类型上更加匹配）。 由于构造方法3参数数量 < argsToUse.length，
             * 参数数量上不匹配，也不应该选。所以 argsToUse.length > paramTypes.length 这个条件用途是：
             * 在当前找到候选构造器的情况下，如果接下来的构造器参数个数小于传入的参数个数，就没必要继续找下去了。
             */
            if (constructorToUse != null && argsToUse.length > paramTypes.length) {
                break;
            }

            // 构造方法参数数量低于配置的参数数量，则忽略当前构造方法。
            if (paramTypes.length < minNrOfArgs) {
                continue;
            }

            ArgumentsHolder argsHolder;
            if (resolvedValues != null) {
                try {
                    /*
                     * 判断否则方法是否有 ConstructorProperties 注解，若有，则取注解中的值。比如下面的代码：
                     * 
                     *  public class Persion {
                     *      private String name;
                     *      private Integer age;
                     *
                     *      @ConstructorProperties(value = {"huzb", "20"})
                     *      public Persion(String name, Integer age) {
                     *          this.name = name;
                     *          this.age = age;
                     *      }
                     * }
                     */
                    String[] paramNames = ConstructorPropertiesChecker.evaluate(candidate, paramTypes.length);
                    if (paramNames == null) {
                        ParameterNameDiscoverer pnd = this.beanFactory.getParameterNameDiscoverer();
                        if (pnd != null) {
                            /*
                             * 获取构造方法参数名称列表，比如有这样一个构造方法:
                             *   public Person(String name, int age, String sex)
                             *   
                             * 调用 getParameterNames 方法返回 paramNames = [name, age, sex]
                             * 这里要注意 Java 的反射是无法获取参数名的，获取到的是 arg0,arg1...
                             * Spring 使用 ASM 字节码操作框架来获取方法参数的名称。
                             */
                            paramNames = pnd.getParameterNames(candidate);
                        }
                    }

                    /* 
                     * 创建参数值列表，返回 argsHolder 会包含进行类型转换后的参数值，比如下面的配置:
                     *
                     *     <bean id="persion" class="com.huzb.demo.Person">
                     *         <constructor-arg name="name" value="xiaoming"/>
                     *         <constructor-arg name="age" value="1"/>
                     *         <constructor-arg name="sex" value="man"/>
                     *     </bean>
                     *
                     * Person 的成员变量 age 是 Integer 类型的，但由于在 Spring 配置中只能配成 String 类型，所以这里要进行类型转换。
                     * 注解方式下，这里会自动注入按类型匹配的参数
                     */
                    argsHolder = createArgumentArray(beanName, mbd, resolvedValues, bw, paramTypes, paramNames,
                            getUserDeclaredConstructor(candidate), autowiring);
                }
                catch (UnsatisfiedDependencyException ex) {
                    if (this.beanFactory.logger.isTraceEnabled()) {
                        this.beanFactory.logger.trace(
                                "Ignoring constructor [" + candidate + "] of bean '" + beanName + "': " + ex);
                    }
                    if (causes == null) {
                        causes = new LinkedList<UnsatisfiedDependencyException>();
                    }
                    causes.add(ex);
                    continue;
                }
            }
            else {
                if (paramTypes.length != explicitArgs.length) {
                    continue;
                }
                argsHolder = new ArgumentsHolder(explicitArgs);
            }

            /*
             * 计算参数值（argsHolder.arguments）每个参数类型与构造方法参数列表（paramTypes）中参数的类型差异量，
             * 差异量越大表明参数类型差异越大。参数类型差异越大，表明当前构造方法并不是一个最合适的候选项。
             * 引入差异量（typeDiffWeight）变量目的：是将候选构造方法的参数列表类型与参数值列表类型的差异进行量化，通过量化
             * 后的数值筛选出最合适的构造方法。
             */
            int typeDiffWeight = (mbd.isLenientConstructorResolution() ?
                    argsHolder.getTypeDifferenceWeight(paramTypes) : argsHolder.getAssignabilityWeight(paramTypes));
            if (typeDiffWeight < minTypeDiffWeight) {
                constructorToUse = candidate;
                argsHolderToUse = argsHolder;
                argsToUse = argsHolder.arguments;
                minTypeDiffWeight = typeDiffWeight;
                ambiguousConstructors = null;
            }
            /* 
             * 如果两个构造方法与参数值类型列表之间的差异量一致，那么这两个方法都可以作为候选项，这个时候就出现歧义了，
             * 这里先把有歧义的构造方法放入 ambiguousConstructors 集合中
             */
            else if (constructorToUse != null && typeDiffWeight == minTypeDiffWeight) {
                if (ambiguousConstructors == null) {
                    ambiguousConstructors = new LinkedHashSet<Constructor<?>>();
                    ambiguousConstructors.add(constructorToUse);
                }
                ambiguousConstructors.add(candidate);
            }
        }

        // 若上面未能筛选出合适的构造方法，这里将抛出 BeanCreationException 异常
        if (constructorToUse == null) {
            if (causes != null) {
                UnsatisfiedDependencyException ex = causes.removeLast();
                for (Exception cause : causes) {
                    this.beanFactory.onSuppressedException(cause);
                }
                throw ex;
            }
            throw new BeanCreationException(mbd.getResourceDescription(), beanName,
                    "Could not resolve matching constructor " +
                    "(hint: specify index/type/name arguments for simple parameters to avoid type ambiguities)");
        }
        /*
         * 如果 constructorToUse != null，且 ambiguousConstructors 也不为空，表明解析出了多个的合适的构造方法，
         * 此时就出现歧义了。Spring 不会擅自决定使用哪个构造方法，所以抛出异常。
         */
        else if (ambiguousConstructors != null && !mbd.isLenientConstructorResolution()) {
            throw new BeanCreationException(mbd.getResourceDescription(), beanName,
                    "Ambiguous constructor matches found in bean '" + beanName + "' " +
                    "(hint: specify index/type/name arguments for simple parameters to avoid type ambiguities): " +
                    ambiguousConstructors);
        }

        if (explicitArgs == null) {
            /*
             * 缓存相关信息，比如：
             *   1. 已解析出的构造方法对象 resolvedConstructorOrFactoryMethod
             *   2. 构造方法参数列表是否已解析标志 constructorArgumentsResolved
             *   3. 参数值列表 resolvedConstructorArguments 或 preparedConstructorArguments
             *
             * 这些信息可用在其他地方，用于进行快捷判断
             */
            argsHolderToUse.storeCache(mbd, constructorToUse);
        }
    }

    try {
        Object beanInstance;

        if (System.getSecurityManager() != null) {
            final Constructor<?> ctorToUse = constructorToUse;
            final Object[] argumentsToUse = argsToUse;
            beanInstance = AccessController.doPrivileged(new PrivilegedAction<Object>() {
                @Override
                public Object run() {
                    return beanFactory.getInstantiationStrategy().instantiate(
                            mbd, beanName, beanFactory, ctorToUse, argumentsToUse);
                }
            }, beanFactory.getAccessControlContext());
        }
        else {
            // 调用实例化策略创建实例，默认情况下使用反射创建实例。
            // 如果 bean 的配置信息中，包含 lookup-method 和 replace-method，则通过 CGLIB 增强 bean 实例
            beanInstance = this.beanFactory.getInstantiationStrategy().instantiate(
                    mbd, beanName, this.beanFactory, constructorToUse, argsToUse);
        }

        // 设置 beanInstance 到 BeanWrapperImpl 对象中
        bw.setBeanInstance(beanInstance);
        return bw;
    }
    catch (Throwable ex) {
        throw new BeanCreationException(mbd.getResourceDescription(), beanName,
                "Bean instantiation via constructor failed", ex);
    }
}
```
上面的方法逻辑比较复杂，做了不少事情，该方法的核心逻辑是根据参数值类型筛选合适的构造方法。解析出合适的构造方法后，剩下的工作就是构建 bean 对象了，这个工作交给了实例化策略去做。下面罗列一下这个方法的工作流程吧：
1. 创建 BeanWrapperImpl 对象
2. 解析构造方法参数，并算出 minNrOfArgs
3. 获取构造方法列表，并排序
4. 遍历排序好的构造方法列表，筛选合适的构造方法
 1. 获取构造方法参数列表中每个参数的名称
 2. 再次解析参数，此次解析会将value 属性值进行类型转换，由 String 转为合适的类型；注解方式下会自动注入对应类型的参数。
 3. 计算构造方法参数列表与参数值列表之间的类型差异量，以筛选出更为合适的构造方法
5. 缓存已筛选出的构造方法以及参数值列表，若再次创建 bean 实例时，可直接使用，无需再次进行筛选
6. 使用初始化策略创建 bean 对象
7. 将 bean 对象放入 BeanWrapperImpl 对象中，并返回该对象

##### 6.1.2、无参构造器方式
// AbstractAutowireCapableBeanFactory 1252
```java
protected BeanWrapper instantiateBean(final String beanName, final RootBeanDefinition mbd) {
    try {
        Object beanInstance;
        final BeanFactory parent = this;
        // if 条件分支里的一大坨是 Java 安全相关的代码，可以忽略，直接看 else 分支
        if (System.getSecurityManager() != null) {
            beanInstance = AccessController.doPrivileged(new PrivilegedAction<Object>() {
                @Override
                public Object run() {
                    return getInstantiationStrategy().instantiate(mbd, beanName, parent);
                }
            }, getAccessControlContext());
        }
        else {
            /**
             * 调用实例化策略创建实例，默认情况下使用反射创建对象。如果 bean 的配置信息中
             * 包含 lookup-method 和 replace-method，则通过 CGLIB 创建 bean 对象
             */
            beanInstance = getInstantiationStrategy().instantiate(mbd, beanName, parent);
        }
        // 创建 BeanWrapperImpl 对象
        BeanWrapper bw = new BeanWrapperImpl(beanInstance);
        initBeanWrapper(bw);
        return bw;
    }
    catch (Throwable ex) {
        throw new BeanCreationException(
                mbd.getResourceDescription(), beanName, "Instantiation of bean failed", ex);
    }
}

public Object instantiate(RootBeanDefinition bd, String beanName, BeanFactory owner) {
    // 检测 bean 配置中是否配置了 lookup-method 或 replace-method，若配置了，则需使用 CGLIB 构建 bean 对象
    if (bd.getMethodOverrides().isEmpty()) {
        Constructor<?> constructorToUse;
        synchronized (bd.constructorArgumentLock) {
            constructorToUse = (Constructor<?>) bd.resolvedConstructorOrFactoryMethod;
            if (constructorToUse == null) {
                final Class<?> clazz = bd.getBeanClass();
                if (clazz.isInterface()) {
                    throw new BeanInstantiationException(clazz, "Specified class is an interface");
                }
                try {
                    if (System.getSecurityManager() != null) {
                        constructorToUse = AccessController.doPrivileged(new PrivilegedExceptionAction<Constructor<?>>() {
                            @Override
                            public Constructor<?> run() throws Exception {
                                return clazz.getDeclaredConstructor((Class[]) null);
                            }
                        });
                    }
                    else {
                        // 获取默认构造方法
                        constructorToUse = clazz.getDeclaredConstructor((Class[]) null);
                    }
                    // 设置 resolvedConstructorOrFactoryMethod
                    bd.resolvedConstructorOrFactoryMethod = constructorToUse;
                }
                catch (Throwable ex) {
                    throw new BeanInstantiationException(clazz, "No default constructor found", ex);
                }
            }
        }
        // 通过无参构造方法创建 bean 对象
        return BeanUtils.instantiateClass(constructorToUse);
    }
    else {
        // 使用 CGLIB 创建 bean 对象
        return instantiateWithMethodInjection(bd, beanName, owner);
    }
}
```
到这里，我们就算实例化完成了。我们开始说怎么进行属性注入。
#### 6.2、属性注入
// AbstractAutowireCapableBeanFactory 1319
```java
protected void populateBean(String beanName, RootBeanDefinition mbd, BeanWrapper bw) {
   // bean 实例的所有属性都在这里了
   PropertyValues pvs = mbd.getPropertyValues();

   if (bw == null) {
      if (!pvs.isEmpty()) {
         throw new BeanCreationException(
               mbd.getResourceDescription(), beanName, "Cannot apply property values to null instance");
      }
      else {
         return;
      }
   }

   // 到这步的时候，bean 实例化完成（通过工厂方法或构造方法），但是还没开始属性设值，
   // InstantiationAwareBeanPostProcessor 的实现类可以在这里对 bean 进行状态设置，比如忽略属性值的设置
   boolean continueWithPropertyPopulation = true;
   if (!mbd.isSynthetic() && hasInstantiationAwareBeanPostProcessors()) {
      for (BeanPostProcessor bp : getBeanPostProcessors()) {
         if (bp instanceof InstantiationAwareBeanPostProcessor) {
            InstantiationAwareBeanPostProcessor ibp = (InstantiationAwareBeanPostProcessor) bp;
            // 如果返回 false，代表不需要进行后续的属性设值，也不需要再经过其他的 BeanPostProcessor 的处理
            if (!ibp.postProcessAfterInstantiation(bw.getWrappedInstance(), beanName)) {
               continueWithPropertyPopulation = false;
               break;
            }
         }
      }
   }

   if (!continueWithPropertyPopulation) {
      return;
   }

   if (mbd.getResolvedAutowireMode() == RootBeanDefinition.AUTOWIRE_BY_NAME ||
         mbd.getResolvedAutowireMode() == RootBeanDefinition.AUTOWIRE_BY_TYPE) {
      MutablePropertyValues newPvs = new MutablePropertyValues(pvs);

      // 通过名字找到所有属性值，如果是 bean 依赖，先初始化依赖的 bean。记录依赖关系
      if (mbd.getResolvedAutowireMode() == RootBeanDefinition.AUTOWIRE_BY_NAME) {
         autowireByName(beanName, mbd, bw, newPvs);
      }

      // 通过类型装配。复杂一些
      if (mbd.getResolvedAutowireMode() == RootBeanDefinition.AUTOWIRE_BY_TYPE) {
         autowireByType(beanName, mbd, bw, newPvs);
      }

      pvs = newPvs;
   }

   boolean hasInstAwareBpps = hasInstantiationAwareBeanPostProcessors();
   boolean needsDepCheck = (mbd.getDependencyCheck() != RootBeanDefinition.DEPENDENCY_CHECK_NONE);

   if (hasInstAwareBpps || needsDepCheck) {
      PropertyDescriptor[] filteredPds = filterPropertyDescriptorsForDependencyCheck(bw, mbd.allowCaching);
      if (hasInstAwareBpps) {
         for (BeanPostProcessor bp : getBeanPostProcessors()) {
            if (bp instanceof InstantiationAwareBeanPostProcessor) {
               InstantiationAwareBeanPostProcessor ibp = (InstantiationAwareBeanPostProcessor) bp;
               // 这里有个非常有用的 BeanPostProcessor 进到这里: AutowiredAnnotationBeanPostProcessor
               // 对采用 @Autowired、@Value 注解的依赖进行设值
               pvs = ibp.postProcessPropertyValues(pvs, filteredPds, bw.getWrappedInstance(), beanName);
               if (pvs == null) {
                  return;
               }
            }
         }
      }
      if (needsDepCheck) {
         checkDependencies(beanName, mbd, filteredPds, pvs);
      }
   }
   // 设置 bean 实例的属性值
   applyPropertyValues(beanName, mbd, bw, pvs);
}
```
上面的源码注释的比较详细了，下面我们来总结一下这个方法的执行流程。如下：
1. 获取属性列表 pvs
2. 在属性未注入之前，使用后置处理器进行状态设置
3. 根据名称或类型解析相关依赖
4. 再次应用后置处理，用于实现基于注解的属性注入
5. 将属性应用到 bean 对象中

注意第3步，也就是根据名称或类型解析相关依赖。该逻辑只会解析依赖，并不会将解析出的依赖立即注入到 bean 对象中。这里解析出的属性值是在 applyPropertyValues 方法中统一被注入到 bean 对象中的。我们常用到的注解式属性注入比较多，所以这里就看一下`基于注解的属性注入`。

##### 6.2.1、基于注解的属性注入
注解形式的属性注入是通过 `AutowiredAnnotationBeanPostProcessor` 的 `postProcessProperties` 方法实现的。源码如下：
// AutowiredAnnotationBeanPostProcessor 371
```java
@Override
public PropertyValues postProcessProperties(PropertyValues pvs, Object bean, String beanName) {
    // 找到要以注解形式注入的属性信息
    InjectionMetadata metadata = findAutowiringMetadata(beanName, bean.getClass(), pvs);
    try {
        // 开始注入
        metadata.inject(bean, beanName, pvs);
    }
    catch (BeanCreationException ex) {
        throw ex;
    }
    catch (Throwable ex) {
        throw new BeanCreationException(beanName, "Injection of autowired dependencies failed", ex);
    }
    return pvs;
}

public void inject(Object target, @Nullable String beanName, @Nullable PropertyValues pvs) throws Throwable {
    Collection<InjectedElement> checkedElements = this.checkedElements;
    Collection<InjectedElement> elementsToIterate =
            (checkedElements != null ? checkedElements : this.injectedElements);
    if (!elementsToIterate.isEmpty()) {
        for (InjectedElement element : elementsToIterate) {
            if (logger.isTraceEnabled()) {
                logger.trace("Processing injected element of bean '" + beanName + "': " + element);
            }
            // 对每个属性依次注入
            element.inject(target, beanName, pvs);
        }
    }
}

@Override
protected void inject(Object bean, @Nullable String beanName, @Nullable PropertyValues pvs) throws Throwable {
    // 要注入的字段
    Field field = (Field) this.member;
    Object value;
    // 会把注入过的属性缓存起来
    if (this.cached) {
        value = resolvedCachedArgument(beanName, this.cachedFieldValue);
    }
    else {
         // 字段的描述，包括字段名、是否必需、所属类、注解信息等
        DependencyDescriptor desc = new DependencyDescriptor(field, this.required);
        desc.setContainingClass(bean.getClass());
        Set<String> autowiredBeanNames = new LinkedHashSet<>(1);
        Assert.state(beanFactory != null, "No BeanFactory available");
        // 类型转换器，用于将 String 类型转换成其它类型
        TypeConverter typeConverter = beanFactory.getTypeConverter();
        try {
            // 核心，实际解析属性的地方，返回的是依赖的实例
            value = beanFactory.resolveDependency(desc, beanName, autowiredBeanNames, typeConverter);
        }
        catch (BeansException ex) {
            throw new UnsatisfiedDependencyException(null, beanName, new InjectionPoint(field), ex);
        }
        synchronized (this) {
            if (!this.cached) {
                if (value != null || this.required) {
                    this.cachedFieldValue = desc;
                    registerDependentBeans(beanName, autowiredBeanNames);
                    if (autowiredBeanNames.size() == 1) {
                        String autowiredBeanName = autowiredBeanNames.iterator().next();
                        if (beanFactory.containsBean(autowiredBeanName) &&
                                beanFactory.isTypeMatch(autowiredBeanName, field.getType())) {
                            this.cachedFieldValue = new ShortcutDependencyDescriptor(
                                    desc, autowiredBeanName, field.getType());
                        }
                    }
                }
                else {
                    this.cachedFieldValue = null;
                }
                this.cached = true;
            }
        }
    }
    if (value != null) {
        ReflectionUtils.makeAccessible(field);
        // 通过反射注入
        field.set(bean, value);
    }
}

public Object resolveDependency(DependencyDescriptor descriptor, String requestingBeanName,
        Set<String> autowiredBeanNames, TypeConverter typeConverter) throws BeansException {

    descriptor.initParameterNameDiscovery(getParameterNameDiscoverer());
    if (javaUtilOptionalClass == descriptor.getDependencyType()) {
        return new OptionalDependencyFactory().createOptionalDependency(descriptor, requestingBeanName);
    }
    else if (ObjectFactory.class == descriptor.getDependencyType() ||
            ObjectProvider.class == descriptor.getDependencyType()) {
        return new DependencyObjectProvider(descriptor, requestingBeanName);
    }
    else if (javaxInjectProviderClass == descriptor.getDependencyType()) {
        return new Jsr330ProviderFactory().createDependencyProvider(descriptor, requestingBeanName);
    }
    else {
        Object result = getAutowireCandidateResolver().getLazyResolutionProxyIfNecessary(
                descriptor, requestingBeanName);
        if (result == null) {
            // 核心，解析依赖
            result = doResolveDependency(descriptor, requestingBeanName, autowiredBeanNames, typeConverter);
        }
        return result;
    }
}

public Object doResolveDependency(DependencyDescriptor descriptor, String beanName,
        Set<String> autowiredBeanNames, TypeConverter typeConverter) throws BeansException {

    InjectionPoint previousInjectionPoint = ConstructorResolver.setCurrentInjectionPoint(descriptor);
    try {
        // 该方法最终调用了 beanFactory.getBean(String, Class)，从容器中获取依赖
        Object shortcut = descriptor.resolveShortcut(this);
        // 如果容器中存在所需依赖，这里进行断路操作，提前结束依赖解析逻辑
        if (shortcut != null) {
            return shortcut;
        }

        Class<?> type = descriptor.getDependencyType();
        // 处理 @value 注解
        Object value = getAutowireCandidateResolver().getSuggestedValue(descriptor);
        if (value != null) {
            if (value instanceof String) {
                String strVal = resolveEmbeddedValue((String) value);
                BeanDefinition bd = (beanName != null && containsBean(beanName) ? getMergedBeanDefinition(beanName) : null);
                value = evaluateBeanDefinitionString(strVal, bd);
            }
            TypeConverter converter = (typeConverter != null ? typeConverter : getTypeConverter());
            return (descriptor.getField() != null ?
                    converter.convertIfNecessary(value, type, descriptor.getField()) :
                    converter.convertIfNecessary(value, type, descriptor.getMethodParameter()));
        }

        // 解析数组、list、map 等类型的依赖
        Object multipleBeans = resolveMultipleBeans(descriptor, beanName, autowiredBeanNames, typeConverter);
        if (multipleBeans != null) {
            return multipleBeans;
        }

        /*
         * findAutowireCandidates 这个方法逻辑比较复杂，它返回的是一个<名称，类型/实例>的候选列表。比如下面的配置：
         *
         *   <bean name="mongoDao" class="com.huzb.demo.MongoDao" primary="true"/>
         *   <bean name="service" class="com.huzb.demo.Service" autowire="byType"/>
         *   <bean name="mysqlDao" class="com.huzb.demo.MySqlDao"/>
         *
         * 我们假设这个属性的类型是 Dao，而 mongoDao 和 mysqlDao 都继承了 Dao 接口，mongoDao 已被实例化，mysqlDao
         * 尚未实例化，那么返回的候选列表就是：
         *
         *   matchingBeans = [ <"mongoDao", Object@MongoDao>, <"mysqlDao", Class@MySqlDao> ]
         * 
         * 方法内部的工作流程如下：
         *   1. 方法开始时有一个 type 记录需要的属性的类型信息。
         *   2. 类型如果是容器对象（我们在容器准备时放进 resolvableDependencies 的），那直接从容器中拿到，加入候选列表。
         *   3. 根据类型信息从 BeanFactory 中获取某种类型 bean 的名称列表，比如按上面配置拿到的就是["mongoDao","mysqlDao"]
         *   4. 遍历上一步得到的名称列表，并判断 bean 名称对应的 bean 是否是合适的候选项，若是合适，则把实例对象（已实例化）
         *       或类型（未实例化）加入候选列表
         *   5. 返回候选列表
         */
        Map<String, Object> matchingBeans = findAutowireCandidates(beanName, type, descriptor);
        if (matchingBeans.isEmpty()) {
            if (isRequired(descriptor)) {
                // 抛出 NoSuchBeanDefinitionException 异常
                raiseNoMatchingBeanFound(type, descriptor.getResolvableType(), descriptor);
            }
            return null;
        }

        String autowiredBeanName;
        Object instanceCandidate;

        if (matchingBeans.size() > 1) {
            /*
             * matchingBeans.size() > 1，则表明存在多个可注入的候选项，这里判断使用哪一个候选项。
             * 候选项的判定规则是：
             * 1）声明了 primary 的优先级最高
             * 2）实现了排序接口，如 Ordered 的优先级比没实现排序接口的高；同样实现了排序接口的会通过比较器比较
             * 3）还没有得到结果的话，则按字段名进行匹配
             */
            autowiredBeanName = determineAutowireCandidate(matchingBeans, descriptor);
            if (autowiredBeanName == null) {
                if (isRequired(descriptor) || !indicatesMultipleBeans(type)) {
                    // 抛出 NoUniqueBeanDefinitionException 异常
                    return descriptor.resolveNotUnique(type, matchingBeans);
                }
                else {
                    return null;
                }
            }
            // 根据解析出的 autowiredBeanName，获取相应的候选项
            instanceCandidate = matchingBeans.get(autowiredBeanName);
        }
        else { // 只有一个候选项，直接取出来即可
            Map.Entry<String, Object> entry = matchingBeans.entrySet().iterator().next();
            autowiredBeanName = entry.getKey();
            instanceCandidate = entry.getValue();
        }

        if (autowiredBeanNames != null) {
            autowiredBeanNames.add(autowiredBeanName);
        }

        // 返回候选项实例，如果实例是 Class 类型，则调用 beanFactory.getBean(String, Class) 获取相应的 bean。否则直接返回即可
        return (instanceCandidate instanceof Class ?
                descriptor.resolveCandidate(autowiredBeanName, type, this) : instanceCandidate);
    }
    finally {
        ConstructorResolver.setCurrentInjectionPoint(previousInjectionPoint);
    }
}
```
代码调用很长，实际的逻辑总结起来有：
1. 找到要以注解形式注入的属性信息
2. 依次对每个字段操作
3. 构造字段的描述，包括字段名、是否必需、所属类、注解信息等
4. 获取属性值
 1. @Value 设置的值，将 String 转成对应类型后返回
 2. 依赖的类型是个数组或集合，会将符合条件的 bean 全部放在数组或集合中返回
 3. 普通类型返回一个候选列表，然后根据判定规则选出优先级最高的一个
5. 如果得到的属性是个 Class 对象，则调用 getBean 生成实例
6. 通过反射注入

#### 6.3、处理各种回调
属性注入完成后，这一步其实就是处理各种回调了，这块代码比较简单。
// AbstractAutowireCapableBeanFactory 1725
```java
protected Object initializeBean(final String beanName, final Object bean, RootBeanDefinition mbd) {
   if (System.getSecurityManager() != null) {
      AccessController.doPrivileged(new PrivilegedAction<Object>() {
         @Override
         public Object run() {
            invokeAwareMethods(beanName, bean);
            return null;
         }
      }, getAccessControlContext());
   }
   else {
      // 如果 bean 实现了 BeanNameAware、BeanClassLoaderAware 或 BeanFactoryAware 接口，回调
      invokeAwareMethods(beanName, bean);
   }

   Object wrappedBean = bean;
   if (mbd == null || !mbd.isSynthetic()) {
      // BeanPostProcessor 的 postProcessBeforeInitialization 回调
      wrappedBean = applyBeanPostProcessorsBeforeInitialization(wrappedBean, beanName);
   }

   try {
      // 处理 bean 中定义的 init-method，
      // 或者如果 bean 实现了 InitializingBean 接口，调用 afterPropertiesSet() 方法
      invokeInitMethods(beanName, wrappedBean, mbd);
   }
   catch (Throwable ex) {
      throw new BeanCreationException(
            (mbd != null ? mbd.getResourceDescription() : null),
            beanName, "Invocation of init method failed", ex);
   }

   if (mbd == null || !mbd.isSynthetic()) {
      // BeanPostProcessor 的 postProcessAfterInitialization 回调
      wrappedBean = applyBeanPostProcessorsAfterInitialization(wrappedBean, beanName);
   }
   return wrappedBean;
}
```
大家发现没有，BeanPostProcessor 的两个回调都发生在这边，只不过中间处理了 init-method，是不是和原来的认知有点不一样了？

## 总结

目前为止，我们已经走完了创建一个 bean 对象的流程。这个流程分为两步：创建对象的前置处理和真正创建对象的过程。创建对象的前置处理确保了对象能按用户定义的方式创建，这些步骤包括：
1. 触发初始化操作
2. 合并父 beanDefinition 与子 beanDefinition
3. 过滤掉抽象、懒加载的、非单例的 bean
4. 预处理 FactoryBean（加'&'，懒加载判断）
5. 别名转化
6. 尝试从缓存中获取
7. 检查 BeanDefinition 是否存在，不存在就去父容器创建
8. 先初始化 depends-on 中定义的依赖
9. 准备方法覆写
10. 准备创建对象
11. 实例化对象
12. 属性注入
13. 处理回调
14. 对 FactoryBean 额外处理
15. 缓存对象
16. 返回 bean

创建对象这个过程是比较重要的，它一共有三步：实例化对象——属性注入——处理回调。Spring 实例化对象分为工厂方式和构造器方式，构造器方式有分为有参构造器和无参构造器。有参构造器会根据传入的参数自动选择合适的构造器实例化对象。实例化之后 Spring 又会为对象注入属性。这里又分为配置文件的方式和注解的方式，注解方式有一系列规则选择最合适的实例注入。最后 Spring 调用 BeanPostProcessor 的前置回调和后置回调，我们发现这两个回调是在同一个方法中实现的，只不过中间处理了 init-method 方法。然后 Spring 会把对象放入缓存中，以后可以直接取出。

## 附录
### 1、合并父 BeanDefinition 与子 BeanDefinition
Spring 支持配置继承，在标签中可以使用 parent 属性配置父类 bean。这样子类 bean 可以继承父类 bean 的配置信息，同时也可覆盖父类中的配置。比如下面的配置：
```xml
<bean id="hello" class="com.huzb.demo.Hello">
    <property name="name" value="hello"/>
    <property name="content" value="I`m hello-parent"/>
</bean>
<bean id="hello-child" parent="hello">
    <property name="content" value="I`m hello-child"/>
</bean>
```
hello-child 继承了 hello 的两个属性，但是对 content 属性进行了覆写。子 bean 还会继承父 bean 的 scope、构造器参数值、属性值、init-method、destroy-method 等等。
### 2、FactoryBean
FactoryBean 适用于 Bean 的创建过程比较复杂的场景，比如数据库连接池的创建等。这里我们用一个简单的例子演示：
```java
public class CarFactoryBean implements FactoryBean<Car> {
    @Override
    public Car getObject() throws Exception {
        Car car = new Car();
        return car;
    }

    @Override
    public Class<?> getObjectType() {
        return Car.class;
    }
    
    @Override
    public boolean isSingleton(){
        return true;
    }
}
```
我们可以通过这两种方式获取生成的 bean：
```java
        // 注意这里的 Bean Name 是 FactoryBean 的类名开头小写而不是 Bean 的类名开头小写
        Car car1 = (Car) applicationContext.getBean("carFactoryBean");
        Car car2 = (Car) applicationContext.getBean(Car.class);
```
FactoryBean 本身也是 bean 想要获取的话，也有两种方式：
```java
        // 注意加了'&'
        CarFactoryBean carFactoryBean1 = (CarFactoryBean) applicationContext.getBean("&carFactoryBean");
        CarFactoryBean carFactoryBean2 = (CarFactoryBean) applicationContext.getBean(CarFactoryBean.class);
```
### 3、方法覆写
#### 3.1、lookup-method
我们通过 BeanFactory getBean 方法获取 bean 实例时，对于 singleton 类型的 bean，BeanFactory 每次返回的都是同一个 bean。对于 prototype 类型的 bean，BeanFactory 则会返回一个新的 bean。现在考虑这样一种情况，一个 singleton 类型的 bean 中有一个 prototype 类型的成员变量。BeanFactory 在实例化 singleton 类型的 bean 时，会向其注入一个 prototype 类型的实例。但是 singleton 类型的 bean 只会实例化一次，那么它内部的 prototype 类型的成员变量也就不会再被改变。但如果我们每次从 singleton bean 中获取这个 prototype 成员变量时，都想获取一个新的对象。这个时候怎么办？
```java
@Component
public class NewsProvider {
    @Autowired
    News news; // prototype bean

    public News getNews() {
        return news;
    }
}
```
这种情况下每次调用 getNews 获得的都是同一个对象。我们可以使用@Lookup 解决这个问题：
```java
@Component
public class NewsProvider {
    @Autowired
    News news; // prototype bean

    @Lookup
    public News getNews() {
        return news;
    }
}
```
标注了@Lookup 后 Spring 会采用 CGLIB 生成字节码的方式来生成一个子类，这个子类的 getNews 方法每次返回的都是一个新的 News 对象。
#### 3.2、replaced-method
replaced-method 的作用是替换掉 bean 中的一些方法，同样是基于 CGLIB 实现的。首先定义一个 bean：
```java
public class Car {

    public void run() {
        System.out.print("run...");
    }
}
```
然后定义一个方法覆写类，需要继承 MethodReplacer 接口：
```java
public class CarReplacer implements MethodReplacer {
    @Override
    public Object reimplement(Object obj, Method method, Object[] args) throws Throwable {
        System.out.print("replacer...");
        return null;
    }
}
```
配置文件;
```xml
<bean id="car" class="com.huzb.demo.Car" >
    <replaced-method name="run" replacer="carReplacer"/>
</bean>
<bean id="carReplacer" class="com.huzb.demo.CarReplacer" />
```
这样调用 Car 的实例的 run 方法的时候会打印“replacer...”而不是“run...”。

### 4、工厂模式创建 Bean
这个工厂模式和 FactoryBean 不一样，前者是实例化对象的方式，后者是 Spring 一类特殊的接口，代表一类 bean。Spring 里面的工厂模式分为静态工厂和实例工厂。
#### 4.1、静态工厂
```java
public class CarFactory {
    // 静态方法
    public static Car createCar(String color) {
        if(color == "red"){
            return new Car("red");
        }
        if(color == "white"){
            return new Car("white");
        }
        else{
            return new Car("black");
        }
    }
}
```
配置文件：
```xml
<bean id="myCar" class="com.huzb.demo.CarFactory" factory-method="createCar">
    <constructor-arg value="red" />
</bean>
```
#### 4.2、实例工厂
```java
public class CarFactory {
    // 实例方法
    public Car createCar(String color) {
        if(color == "red"){
            return new Car("red");
        }
        if(color == "white"){
            return new Car("white");
        }
        else{
            return new Car("black");
        }
    }
}
```
配置文件：
```xml
<bean id="carFactory" class="com.huzb.demo.CarFactory"/>

<bean id="myCar" factory-bean="carFactory" factory-method="createCar">
    <constructor-arg value="red" />
</bean>
```
另外注解方式在配置类中声明对象，也是通过实例工厂的方式实现的：
```java
@Configuration
public class DemoApplication {
    @Bean
    public Car car(){
        return new Car();
    }
}
```

## 参考资料
[Spring IOC 容器源码分析](https://javadoop.com/post/spring-ioc)
[Spring IOC 容器源码分析 - 获取单例 bean](http://www.tianxiaobo.com/2018/06/01/Spring-IOC-%E5%AE%B9%E5%99%A8%E6%BA%90%E7%A0%81%E5%88%86%E6%9E%90-%E8%8E%B7%E5%8F%96%E5%8D%95%E4%BE%8B-bean/)
[Spring IOC 容器源码分析 - 获取单例 bean](http://www.tianxiaobo.com/2018/06/04/Spring-IOC-%E5%AE%B9%E5%99%A8%E6%BA%90%E7%A0%81%E5%88%86%E6%9E%90-%E5%88%9B%E5%BB%BA%E5%8D%95%E4%BE%8B-bean/)
[lookup-method和replaced-method使用](https://blog.csdn.net/lightofmiracle/article/details/74988243)