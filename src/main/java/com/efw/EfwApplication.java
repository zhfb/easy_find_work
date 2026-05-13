package com.efw;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * Efw应用程序启动类
 * 自动化求职平台的主入口
 *
 * @author Efw
 * @version 0.0.1-SNAPSHOT
 */
@SpringBootApplication(scanBasePackages = "com.efw")
@EnableScheduling
@EnableAsync
public class EfwApplication {
    public static void main(String[] args) {
        SpringApplication.run(EfwApplication.class, args);
    }
}