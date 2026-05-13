package com.efw.application.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * 中国岗位原型检测器
 * 将 Career-Ops / EFW 的 6 种 AI 原型适配为中国市场的 8 种岗位原型
 */
@Slf4j
@Component
public class ArchetypeDetector {

    public enum Archetype {
        TECH_BACKEND("Tech-Backend", "技术后端", "Java/Go/Python 后端开发、微服务、API 设计"),
        TECH_FRONTEND("Tech-Frontend", "技术前端", "React/Vue/Web 前端、移动端、跨端开发"),
        TECH_DATA("Tech-Data", "技术数据", "大数据、数据分析、数据挖掘、ETL"),
        TECH_OPS("Tech-Ops", "技术运维", "DevOps、SRE、运维开发、云原生、CI/CD"),
        PRODUCT("Product", "产品经理", "产品设计、需求分析、用户增长、B端/C端产品"),
        DESIGN("Design", "设计", "UI/UX 设计、视觉设计、交互设计"),
        OPERATION("Operation", "运营", "用户运营、内容运营、活动运营、新媒体"),
        GENERAL("General", "通用/其他", "不匹配以上类别的岗位");

        private final String code;
        private final String cnName;
        private final String description;

        Archetype(String code, String cnName, String description) {
            this.code = code;
            this.cnName = cnName;
            this.description = description;
        }

        public String getCode() { return code; }
        public String getCnName() { return cnName; }
        public String getDescription() { return description; }
    }

    // 每类原型的关键信号词
    private static final Map<Archetype, List<String>> ARCHETYPE_KEYWORDS = Map.of(
        Archetype.TECH_BACKEND, List.of("后端", "Java", "Spring", "Go", "Golang", "Python", "微服务",
            "MySQL", "Redis", "Kafka", "分布式", "中间件", "API", "REST", "gRPC", "Docker", "架构设计"),
        Archetype.TECH_FRONTEND, List.of("前端", "React", "Vue", "Angular", "Web", "H5", "移动端",
            "Flutter", "小程序", "uni-app", "CSS", "TypeScript", "Node", "跨端"),
        Archetype.TECH_DATA, List.of("大数据", "数据开发", "数据分析", "数据挖掘", "ETL", "Hadoop",
            "Spark", "Flink", "数据仓库", "BI", "数仓", "Hive", "SQL"),
        Archetype.TECH_OPS, List.of("运维", "DevOps", "SRE", "云原生", "CI/CD", "Kubernetes",
            "K8s", "Jenkins", "监控", "自动化运维", "基础设施", "容器化", "Linux"),
        Archetype.PRODUCT, List.of("产品经理", "产品", "需求分析", "用户增长", "PRD", "产品设计",
            "B端", "C端", "功能设计", "用户研究", "增长", "商业化"),
        Archetype.DESIGN, List.of("UI", "UX", "视觉设计", "交互设计", "界面设计", "Figma",
            "Sketch", "用户研究", "设计规范", "品牌设计"),
        Archetype.OPERATION, List.of("运营", "用户运营", "内容运营", "活动运营", "新媒体",
            "社群运营", "增长", "裂变", "投放", "数据分析", "转化")
    );

    /**
     * 检测岗位所属原型
     * @param jobName 岗位名称
     * @param jobDescription 岗位描述/JD
     * @return 检测到的原型
     */
    public Archetype detect(String jobName, String jobDescription) {
        String text = (jobName + " " + (jobDescription != null ? jobDescription : "")).toLowerCase();

        // 统计每类原型的匹配得分
        long[] scores = new long[Archetype.values().length];
        for (int i = 0; i < Archetype.values().length; i++) {
            Archetype type = Archetype.values()[i];
            List<String> keywords = ARCHETYPE_KEYWORDS.getOrDefault(type, List.of());
            scores[i] = keywords.stream()
                .filter(kw -> text.contains(kw.toLowerCase()))
                .count();
        }

        // 找到最高分
        int maxIndex = 0;
        for (int i = 1; i < scores.length; i++) {
            if (scores[i] > scores[maxIndex]) {
                maxIndex = i;
            }
        }

        // 如果最高分也为 0，返回通用
        if (scores[maxIndex] == 0) {
            return Archetype.GENERAL;
        }

        return Archetype.values()[maxIndex];
    }

    public List<Archetype> getAllArchetypes() {
        return Arrays.asList(Archetype.values());
    }
}
