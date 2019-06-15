---
title: Spring MVC 源码浅析——容器创建过程
tags: 
	- Java
	- Spring
toc: true
date: 2019-03-26 23:45:41
---
Spring MVC  中会配置两个容器：一个用于加载 Web 层的类，比如 Controller、HandlerMapping、ViewResolver 等，叫 web 容器；另一个容器用于加载业务逻辑相关的类，比如 service、dao 层的一些类，叫业务容器。这两个容器是父子关系，业务容器是 web 容器的父容器。父容器中的 bean 对子容器可见，而子容器中的 bean 对父容器不可见。在初始化时，父容器会先于子容器初始化，这是因为子容器中的一些 bean 可能会依赖父容器。

注：在 Sping Boot 中不再有父子容器的概念，因此这是 Spring MVC 独有的。因为面试会问到这部分概念，所以在这里总结一下。

## 一、父容器创建

web 应用程序启动时，servlet 容器会创建一个全局共享的上下文： ServletContext，然后会读取 web.xml 文件，将读取到的<context-param>转化为键值对，将读取到的<listener>创建出来。如果我们要使用 Spring 的话，就要在 web.xml 中添加如下配置：
```xml
<web-app>
    <!-- 省略其他配置 -->
     <listener>
        <listener-class>org.springframework.web.context.ContextLoaderListener</listener-class>
    </listener>
    
    <context-param>
        <param-name>contextConfigLocation</param-name>
        <param-value>classpath:application.xml</param-value>
    </context-param>
    
    <!-- 省略其他配置 -->
</web-app>
```
tomcat 会在启动时创建 ContextLoaderListener 对象，这个对象会监听 ServletContext 的创建，然后在监听回调函数中创建父容器。我们来看一下它创建父容器的代码：
```java
public class ContextLoaderListener extends ContextLoader implements ServletContextListener {

    // 省略部分代码

    @Override
    public void contextInitialized(ServletContextEvent event) {
        // 初始化父容器
        initWebApplicationContext(event.getServletContext());
    }
}
```
```java
public WebApplicationContext initWebApplicationContext(ServletContext servletContext) {

    // ServletContext 中会存储一个<key，父容器>的键值对，如果这个 key 被其它组件使用了，就会抛出异常
    if (servletContext.getAttribute(WebApplicationContext.ROOT_WEB_APPLICATION_CONTEXT_ATTRIBUTE) != null) {
        throw new IllegalStateException(...);
    }

    //...

    try {
        if (this.context == null) {
            // 创建父容器
            this.context = createWebApplicationContext(servletContext);
        }
        if (this.context instanceof ConfigurableWebApplicationContext) {
            ConfigurableWebApplicationContext cwac = (ConfigurableWebApplicationContext) this.context;
            if (!cwac.isActive()) {
                if (cwac.getParent() == null) {
                     // 加载当前容器的父容器，一般没有，除非特别配置
                    ApplicationContext parent = loadParentContext(servletContext);
                    cwac.setParent(parent);
                }
                // 配置并刷新父容器，这里的刷新过程就是我们之前分析过的 refresh 方法
                configureAndRefreshWebApplicationContext(cwac, servletContext);
            }
        }

        // 在 ServletContext 中创建一个<key，父容器>的键值对，对应方法开头
        servletContext.setAttribute(WebApplicationContext.ROOT_WEB_APPLICATION_CONTEXT_ATTRIBUTE, this.context);

        ClassLoader ccl = Thread.currentThread().getContextClassLoader();
        if (ccl == ContextLoader.class.getClassLoader()) {
            currentContext = this.context;
        }
        else if (ccl != null) {
            currentContextPerThread.put(ccl, this.context);
        }

        return this.context;
    }
    catch (RuntimeException ex) {...}
}
```
进入创建容器的代码：
```java
protected WebApplicationContext createWebApplicationContext(ServletContext sc) {
    // 判断创建什么类型的容器，默认类型为 XmlWebApplicationContext
    Class<?> contextClass = determineContextClass(sc);
    if (!ConfigurableWebApplicationContext.class.isAssignableFrom(contextClass)) {
        throw new ApplicationContextException(...);
    }
    // 通过反射创建容器
    return (ConfigurableWebApplicationContext) BeanUtils.instantiateClass(contextClass);
}
```
```java
protected Class<?> determineContextClass(ServletContext servletContext) {
    /*
     * 读取用户自定义配置，比如：
     * <context-param>
     *     <param-name>contextClass</param-name>
     *     <param-value>XXXConfigWebApplicationContext</param-value>
     * </context-param>
     */
    String contextClassName = servletContext.getInitParameter(CONTEXT_CLASS_PARAM);
    if (contextClassName != null) {
        try {
            return ClassUtils.forName(contextClassName, ClassUtils.getDefaultClassLoader());
        }
        catch (ClassNotFoundException ex) {...}
    }
    else {
        /*
         * 若无自定义配置，则获取默认的容器类型，默认类型为 XmlWebApplicationContext。
         * defaultStrategies 读取的配置文件为 ContextLoader.properties，
         * 该配置文件内容如下：
         * org.springframework.web.context.WebApplicationContext =
         *     org.springframework.web.context.support.XmlWebApplicationContext
         */
        contextClassName = defaultStrategies.getProperty(WebApplicationContext.class.getName());
        try {
            return ClassUtils.forName(contextClassName, ContextLoader.class.getClassLoader());
        }
        catch (ClassNotFoundException ex) {...}
    }
}
```
一句话就是根据配置文件的内容获取父容器的类型，然后通过反射创建容器。接下来再看看配置并刷新容器的代码：
```java
protected void configureAndRefreshWebApplicationContext(ConfigurableWebApplicationContext wac, ServletContext sc) {
    if (ObjectUtils.identityToString(wac).equals(wac.getId())) {
        // 从 ServletContext 中获取用户配置的 contextId 属性
        String idParam = sc.getInitParameter(CONTEXT_ID_PARAM);
        if (idParam != null) {
            // 设置容器 id
            wac.setId(idParam);
        }
        else {
            // 用户未配置 contextId，则设置一个默认的容器 id
            wac.setId(ConfigurableWebApplicationContext.APPLICATION_CONTEXT_ID_PREFIX + 
ObjectUtils.getDisplayString(sc.getContextPath()));
        }
    }

    wac.setServletContext(sc);
    // 获取 contextConfigLocation 配置
    String configLocationParam = sc.getInitParameter(CONFIG_LOCATION_PARAM);
    if (configLocationParam != null) {
        wac.setConfigLocation(configLocationParam);
    }
    
    ConfigurableEnvironment env = wac.getEnvironment();
    if (env instanceof ConfigurableWebEnvironment) {
        ((ConfigurableWebEnvironment) env).initPropertySources(sc, null);
    }

    customizeContext(sc, wac);

    // 刷新容器
    wac.refresh();
}
```
说白了也很简单，就是从配置文件获取容器 id，没有的话就默认设置一个，然后获取配置文件的路径，放入容器中，刷新容器，之后就是大家熟悉的过程了。

总结一下父容器的创建过程：
1. 创建 listener 节点中的 ContextLoaderListener 实例
2. 创建过程中初始化 webapplicationContext，也即是父容器对象
3. 从 ServletContext 中获取 contextConfigLocation 的值，这是父容器配置文件的路径，把路径放入父容器中
4. 根据配置信息刷新父容器
5. 将父容器保存在 ServletContext 中

## 二、子容器创建
子容器的加载发生在 DispatcherServlet 初始化的时候，而 DispatcherServlet 的初始化发生在第一个请求到达的时候，因此能确保 Servlet 的初始化发生在 listener 初始化之后。初始化 DispatcherServlet 需要在 web.xml 中添加如下配置：
```xml
<web-app>
    <!-- 省略其他配置 -->
    <servlet>
        <servlet-name>springMVC</servlet-name>
        <servlet-class>org.springframework.web.servlet.DispatcherServlet</servlet-class>
        <!-- 初始化参数，配置springmvc配置文件 -->
        <init-param>
            <param-name>contextConfigLocation</param-name>
            <param-value>classpath:application-web.xml</param-value>
        </init-param>
        <!-- web容器启动时加载该Servlet -->
        <load-on-startup>1</load-on-startup>
    </servlet>
    <servlet-mapping>
        <servlet-name>springMVC</servlet-name>
        <!-- 拦截所有请求 -->
        <url-pattern>/</url-pattern>
    </servlet-mapping>
    <!-- 省略其他配置 -->
</web-app>
```
初始化的入口在 DispatcherServlet 的 init 方法中：
```java
public final void init() throws ServletException {
    if (logger.isDebugEnabled()) {...}

    // 获取 ServletConfig 中的配置信息
    PropertyValues pvs = new ServletConfigPropertyValues(getServletConfig(), this.requiredProperties);
    if (!pvs.isEmpty()) {
        try {
            // 为 DispatcherServlet 对象创建一个 BeanWrapper，方便读/写对象属性。
            BeanWrapper bw = PropertyAccessorFactory.forBeanPropertyAccess(this);
            ResourceLoader resourceLoader = new ServletContextResourceLoader(getServletContext());
            bw.registerCustomEditor(Resource.class, new ResourceEditor(resourceLoader, getEnvironment()));
            initBeanWrapper(bw);
            // 设置配置信息到目标对象中
            bw.setPropertyValues(pvs, true);
        }
        catch (BeansException ex) {
            if (logger.isErrorEnabled()) {...}
            throw ex;
        }
    }

    // 进行后续的初始化
    initServletBean();

    if (logger.isDebugEnabled()) {...}
}
```
上面的源码主要做的事情是将 web.xml 中的配置信息设置到 DispatcherServlet 对象中，容器的初始化在 initServletBean 中：
```java
protected final void initServletBean() throws ServletException {
    // ...
    try {
        // 初始化容器
        this.webApplicationContext = initWebApplicationContext();
        initFrameworkServlet();
    }
    // ...
}
```
```java
protected WebApplicationContext initWebApplicationContext() {
    // 获取父容器
    WebApplicationContext rootContext = WebApplicationContextUtils.getWebApplicationContext(getServletContext());
    WebApplicationContext wac = null;

    // 检查外部是否已经设置了子容器，Spring MVC 中一般 this.webApplicationContext = null，
    // 而 Spring Boot 中 this.webApplicationContext 就是父容器，看后面的代码就可以知道，Spring Boot 不会创建子容器，
    // 只会再刷新一次，初始化一些特殊组件比如 handler、invocation 
    if (this.webApplicationContext != null) {
        wac = this.webApplicationContext;
        if (wac instanceof ConfigurableWebApplicationContext) {
            ConfigurableWebApplicationContext cwac = (ConfigurableWebApplicationContext) wac;
            // Spring Boot 中虽然有外部设置的 this.webApplicationContext，但不会进入下面的代码
            if (!cwac.isActive()) {
                if (cwac.getParent() == null) {
                    // 设置父容器
                    cwac.setParent(rootContext);
                }
                // 配置并刷新容器
                configureAndRefreshWebApplicationContext(cwac);
            }
        }
    }
    if (wac == null) {
        // 尝试从 ServletContext 中获取容器
        wac = findWebApplicationContext();
    }
    if (wac == null) {
        // 创建容器，并设置父容器
        wac = createWebApplicationContext(rootContext);
    }

    if (!this.refreshEventReceived) {
        // 刷新容器
        onRefresh(wac);
    }

    if (this.publishContext) {
        String attrName = getServletContextAttributeName();
        // 将创建好的容器缓存到 ServletContext 中
        getServletContext().setAttribute(attrName, wac);
        if (this.logger.isDebugEnabled()) {...}
    }

    return wac;
}
```
以上就是创建子容器的源码，下面总结一下该容器创建的过程，我们分成 Spring MVC 和 Spring Boot 两条路线：
Spring MVC 路线：
1. 从 ServletContext 中获取父容器
2. 如果已有外部设置的子容器的话，设置父容器、刷新子容器
3. 尝试从 ServletContext 中获取子容器，若子容器不为空，则无需执行步骤4
4. 创建子容器，并设置父容器
5. 刷新子容器
6. 缓存子容器到 ServletContext 中

Spring Boot 路线：
1. 从 ServletContext 中获取父容器
2. 获取 this.webApplicationContext 的“子”容器，其实就是父容器
3. 刷新容器
4. 缓存容器到 ServletContext 中

这里子容器的创建分为两条路线，Spring MVC 路线和 Spring Boot 路线。不过最终它们都会调用 onRefresh 刷新容器。接下来我们看一下 onRefresh 方法做了什么：
```java
protected void onRefresh(ApplicationContext context) {
    initStrategies(context);
}
```
```java
protected void initStrategies(ApplicationContext context) {
    // 初始化 MultipartResolver，用于文件上传
    initMultipartResolver(context);
    // 初始化 LocaleResolver，用于解析用户区域
    initLocaleResolver(context);
    // 初始化 ThemeResolver，用于设置主题
    initThemeResolver(context);
    // 初始化 HandlerMappings，用于映射用户的 URL 和对应的处理类
    initHandlerMappings(context);
    // 初始化 HandlerAdapters，用于执行处理类得到 ModelAndView
    initHandlerAdapters(context);
    // 初始化 HandlerExceptionResolvers，用于统一异常处理
    initHandlerExceptionResolvers(context);
    // 初始化 RequestToViewNameTranslator，用于在处理器返回的 View 为空时根据请求得到视图名称
    initRequestToViewNameTranslator(context);
    // 初始化 ViewResolvers，用于把视图名称转换为真正的视图对象
    initViewResolvers(context);
    // 初始化FlashMapManager，用于重定向数据保存
    initFlashMapManager(context);
}
```
我们重点关注一下 `initHandlerMappings` 和 `initHandlerAdapters` 两个方法：
```java
private void initHandlerMappings(ApplicationContext context) {
    this.handlerMappings = null;

    if (this.detectAllHandlerMappings) {
        // 如果配置的是找到所有 HandlerMapping，则找到容器和父容器中所有的 HandlerMapping
        Map<String, HandlerMapping> matchingBeans =
                BeanFactoryUtils.beansOfTypeIncludingAncestors(context, HandlerMapping.class, true, false);
        if (!matchingBeans.isEmpty()) {
            // 将所有 HandlerMapping 保存在 DispatcherServlet 中
            this.handlerMappings = new ArrayList<>(matchingBeans.values());
            // 对 HandlerMapping 排序
            AnnotationAwareOrderComparator.sort(this.handlerMappings);
        }
    }
    else {
        try {
            // 如果配置的是只找一个 HandlerMapping，则找到容器中名称为 "handlerMapping" 的 HandlerMapping
            HandlerMapping hm = context.getBean("handlerMapping", HandlerMapping.class);
            // 将找到的 HandlerMapping 保存在 DispatcherServlet 中
            this.handlerMappings = Collections.singletonList(hm);
        }
        catch (NoSuchBeanDefinitionException ex) {...}
    }

    // 如果容器中没有 HandlerMapping，就创建一个默认的保存在 DispatcherServlet 中
    if (this.handlerMappings == null) {
        this.handlerMappings = getDefaultStrategies(context, HandlerMapping.class);
    }
}
```
```java
private void initHandlerAdapters(ApplicationContext context) {
    this.handlerAdapters = null;

    if (this.detectAllHandlerAdapters) {
        // 如果配置的是找到所有 HandlerAdapter，则找到容器和父容器中所有的 HandlerAdapter
        Map<String, HandlerAdapter> matchingBeans =
                BeanFactoryUtils.beansOfTypeIncludingAncestors(context, HandlerAdapter.class, true, false);
        if (!matchingBeans.isEmpty()) {
            // 将所有 HandlerAdapter 保存在 DispatcherServlet 中
            this.handlerAdapters = new ArrayList<>(matchingBeans.values());
            // 对 HandlerAdapter 排序
            AnnotationAwareOrderComparator.sort(this.handlerAdapters);
        }
    }
    else {
        try {
            // 如果配置的是只找一个 HandlerAdapter，则找到容器中名称为 "handlerAdapter" 的 HandlerAdapter
            HandlerAdapter ha = context.getBean("handlerAdapter", HandlerAdapter.class);
            // 将找到的 HandlerAdapter 保存在 DispatcherServlet 中
            this.handlerAdapters = Collections.singletonList(ha);
        }
        catch (NoSuchBeanDefinitionException ex) {...}
    }


    // 如果容器中没有 HandlerAdapter，就创建一个默认的保存在 DispatcherServlet 中
    if (this.handlerAdapters == null) {
        this.handlerAdapters = getDefaultStrategies(context, HandlerAdapter.class);
    }
}
```
上面的注释我们可以看到，`initHandlerMappings` 和 `initHandlerAdapters` 这两个方法会从容器中找出 HandlerMapping 和 HandlerAdapter 然后保存在 DispatcherServlet 中。说明 DispatcherServlet 中的 onRefresh 方法并不像我们熟悉的容器刷新一样，它只是把容器中的在 DispatcherServlet 中要用到的组件设置到 DispatcherServlet 中。而实际的 HandlerMapping 和 HandlerAdapter 和普通 bean 一样在创建的时候就初始化了。

## 三、小结

我们来总结一下，Sping MVC 中的容器创建分为父容器的创建和子容器的创建。父容器创建的时机在 Servlet 容器上下文创建的时候，通过监听器 ContextLoaderListener 的回调函数创建父容器。子容器创建的时机在 DispatcherServlet 初始化的时候，一般发生在第一个请求到达，由 Servlet 容器初始化。子容器的创建在我们之前熟知的容器创建步骤之后，还会执行 onRefresh 为 DispatcherServlet 设置几个重要组件，这几个组件用于处理和请求相关的工作。

## 四、参考资料
[Spring MVC 原理探秘 - 容器的创建过程](http://www.tianxiaobo.com/2018/06/30/Spring-MVC-%E5%8E%9F%E7%90%86%E6%8E%A2%E7%A7%98-%E5%AE%B9%E5%99%A8%E7%9A%84%E5%88%9B%E5%BB%BA%E8%BF%87%E7%A8%8B/)
[SpringMVC工作原理之二：HandlerMapping和HandlerAdapter](https://blog.csdn.net/gaoshan12345678910/article/details/81910397)
[Spring与SpringMVC父子容器的关系与初始化](https://blog.csdn.net/dhaiuda/article/details/80026354)