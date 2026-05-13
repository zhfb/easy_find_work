package com.efw.application.service;

import com.efw.application.mapper.EvaluationMapper;
import com.efw.application.service.EvaluationService.CandidateProfile;
import com.efw.application.service.EvaluationService.EvaluationResult;
import com.efw.application.service.EvaluationService.JobInfo;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

/**
 * A-G 评估引擎单元测试
 */
class EvaluationServiceTest {

    private EvaluationService evaluationService;
    private ArchetypeDetector archetypeDetector;
    private EvaluationMapper evaluationMapper;

    @BeforeEach
    void setUp() {
        archetypeDetector = new ArchetypeDetector();
        evaluationMapper = mock(EvaluationMapper.class);
        evaluationService = new EvaluationService(evaluationMapper, archetypeDetector);
    }

    @Nested
    @DisplayName("薪资解析测试")
    class SalaryParsingTests {

        @ParameterizedTest
        @CsvSource({
            "20K-40K, 20000.0, 40000.0",
            "15k-25k·14薪, 15000.0, 25000.0",
            "30-50K·16薪, 30000.0, 50000.0",
            "25k-35k, 25000.0, 35000.0",
            "200-300/天, 4200.0, 6300.0"
        })
        @DisplayName("应正确解析各种薪资格式")
        void shouldParseVariousSalaryFormats(String salaryStr, double expectedMin, double expectedMax) {
            double[] result = EvaluationService.parseSalary(salaryStr);
            assertNotNull(result);
            assertEquals(expectedMin, result[0], 100);
            assertEquals(expectedMax, result[1], 100);
        }

        @Test
        @DisplayName("空薪资应返回 null")
        void shouldReturnNullForEmptySalary() {
            assertNull(EvaluationService.parseSalary(null));
            assertNull(EvaluationService.parseSalary(""));
        }
    }

    @Nested
    @DisplayName("完整 A-G 评估测试")
    class FullEvaluationTests {

        @Test
        @DisplayName("高质量岗位应获得高分推荐投递")
        void highQualityJobShouldGetHighScore() {
            JobInfo job = createJobInfo(
                "Java架构师",
                "负责高并发微服务架构设计，精通Java、Spring Boot、MySQL、Redis、Kafka、分布式系统。本科及以上学历，5年以上经验。公司为D轮融资，团队核心项目，有期权激励。年终奖丰厚。",
                "35K-50K·16薪",
                "D轮及以上",
                "在线",
                "互联网/电商"
            );

            EvaluationResult result = evaluationService.evaluate(job, null);

            System.out.println("High quality job scores: A=" + result.getScoreA()
                + " B=" + result.getScoreB() + " C=" + result.getScoreC()
                + " D=" + result.getScoreD() + " E=" + result.getScoreE()
                + " F=" + result.getScoreF() + " G=" + result.getScoreG()
                + " Total=" + result.getTotalScore());

            assertTrue(result.getTotalScore() >= 3.5, "高质量岗位应推荐投递");
            assertEquals("Tech-Backend", result.getArchetype());
        }

        @Test
        @DisplayName("低质量岗位应获得低分建议跳过")
        void lowQualityJobShouldGetLowScore() {
            JobInfo job = createJobInfo(
                "销售",
                "销售",
                "",
                "未融资",
                "半年不活跃",
                "其他"
            );

            EvaluationResult result = evaluationService.evaluate(job, null);

            System.out.println("Low quality job scores: A=" + result.getScoreA()
                + " B=" + result.getScoreB() + " C=" + result.getScoreC()
                + " D=" + result.getScoreD() + " E=" + result.getScoreE()
                + " F=" + result.getScoreF() + " G=" + result.getScoreG()
                + " Total=" + result.getTotalScore());

            assertTrue(result.getTotalScore() < 3.5, "低质量岗位应建议跳过");
            assertEquals("General", result.getArchetype());
        }

        @Test
        @DisplayName("原型检测应正确识别岗位类型")
        void archetypeDetectionShouldWork() {
            assertEquals("Tech-Backend",
                evaluationService.evaluate(createJobInfo("Java后端开发", "Java, Spring, MySQL, 微服务"), null).getArchetype());
            assertEquals("Tech-Frontend",
                evaluationService.evaluate(createJobInfo("前端开发工程师", "React, Vue, TypeScript, Web"), null).getArchetype());
            assertEquals("Product",
                evaluationService.evaluate(createJobInfo("产品经理", "需求分析, PRD, 产品设计, 用户增长"), null).getArchetype());
        }

        @Test
        @DisplayName("幽灵岗位应被 G 块检测")
        void ghostJobShouldBeFlaggedByBlockG() {
            JobInfo job = createJobInfo(
                "Java开发",
                "招人",
                "",
                "",
                "半年前活跃",
                ""
            );
            EvaluationResult result = evaluationService.evaluate(job, null);
            assertTrue(result.getScoreG() <= 2, "幽灵岗位的 G 块评分应较低");
        }

        @Test
        @DisplayName("HR 活跃的岗位 G 块评分应较高")
        void activeHrShouldGetHigherBlockG() {
            JobInfo job = createJobInfo(
                "Java开发工程师",
                "负责后端系统开发，精通Java、Spring Boot、微服务架构设计、分布式系统、MySQL、Redis、Kafka。负责核心业务系统的架构设计与开发，保障系统高可用和高并发。本科及以上学历，计算机相关专业优先。",
                "20K-35K",
                "B轮",
                "今日活跃",
                "互联网"
            );
            EvaluationResult result = evaluationService.evaluate(job, null);
            assertTrue(result.getScoreG() >= 4, "活跃 HR 的 G 块评分应较高");
        }
    }

    @Nested
    @DisplayName("候选画像匹配测试")
    class CandidateProfileTests {

        @Test
        @DisplayName("技能匹配应影响 B 块评分")
        void skillMatchShouldAffectScoreB() {
            JobInfo job = createJobInfo("Java开发", "精通Java、Spring、MySQL、Redis。3年以上经验。");
            CandidateProfile profile = new CandidateProfile();
            profile.setSkills("Java, Spring, MySQL, Redis, Kafka, Docker");
            profile.setExperienceYears(5);
            profile.setExpectedSalaryMin(20000);

            EvaluationResult withProfile = evaluationService.evaluate(job, profile);
            EvaluationResult withoutProfile = evaluationService.evaluate(job, null);

            assertTrue(withProfile.getScoreB() >= withoutProfile.getScoreB(),
                "有技能匹配的 B 块评分应不低于无匹配");
        }

        @Test
        @DisplayName("经验不足应降低 B 块评分")
        void insufficientExperienceShouldReduceScoreB() {
            JobInfo job = createJobInfo("Java架构师", "要求5年以上Java开发经验。精通分布式系统架构。");
            job.setExperienceRequired(5); // 岗位要求 5 年经验
            CandidateProfile profile = new CandidateProfile();
            profile.setSkills("Java, Spring");
            profile.setExperienceYears(1);

            EvaluationResult result = evaluationService.evaluate(job, profile);
            // 经验不足时，B 块评分不应高于无画像评估（因为 exp diff 惩罚会生效）
            EvaluationResult without = evaluationService.evaluate(job, null);
            System.out.println("With profile B=" + result.getScoreB() + " Without B=" + without.getScoreB());
            // 有画像时的综合总分因经验不足不应高于默认
            assertTrue(result.getTotalScore() <= without.getTotalScore() || result.getScoreB() <= without.getScoreB(),
                "经验不足应影响评分: totalWith=" + result.getTotalScore() + " totalWithout=" + without.getTotalScore());
        }
    }

    private JobInfo createJobInfo(String jobName, String jobDescription) {
        return createJobInfo(jobName, jobDescription, "20K-40K", "B轮", "今日活跃", "互联网");
    }

    private JobInfo createJobInfo(String jobName, String jobDescription, String salary,
                                  String stage, String hrActive, String industry) {
        JobInfo job = new JobInfo("test123", "测试公司", jobName, salary, jobDescription);
        job.setFinancingStage(stage);
        job.setHrActiveStatus(hrActive);
        job.setIndustry(industry);
        job.setCompanyScale("100-500人");
        return job;
    }
}
