package com.efw.application.service;

import com.efw.application.service.ArchetypeDetector.Archetype;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.*;

/**
 * ArchetypeDetector 单元测试
 */
class ArchetypeDetectorTest {

    private ArchetypeDetector detector;

    @BeforeEach
    void setUp() {
        detector = new ArchetypeDetector();
    }

    @ParameterizedTest
    @CsvSource({
        "Java后端开发工程师, 负责微服务架构设计, Tech-Backend",
        "前端架构师, React 和 Vue 开发, Tech-Frontend",
        "大数据开发, Hadoop Spark 数据仓库, Tech-Data",
        "运维工程师, Kubernetes DevOps CI/CD, Tech-Ops",
        "产品经理, 需求分析 PRD 产品设计, Product",
        "UI设计师, Figma 视觉设计 交互, Design",
        "用户运营, 社群运营 内容运营 增长, Operation",
        "随便岗位, 无关键词, General",
    })
    @DisplayName("应正确检测岗位原型")
    void shouldDetectCorrectArchetype(String jobName, String jobDesc, String expectedCode) {
        Archetype result = detector.detect(jobName, jobDesc);
        assertEquals(expectedCode, result.getCode());
    }

    @Test
    @DisplayName("应返回所有 8 种原型")
    void shouldReturnAllArchetypes() {
        assertEquals(8, detector.getAllArchetypes().size());
    }
}
