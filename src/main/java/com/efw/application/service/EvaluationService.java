package com.efw.application.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.efw.application.entity.EvaluationEntity;
import com.efw.application.mapper.EvaluationMapper;
import com.efw.application.service.ArchetypeDetector.Archetype;
import lombok.Data;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * A-G 评估引擎
 * 将 Career-Ops / EFW 的 A-G 七块评估系统适配到 EFW
 * 评分 1-5 分，综合评分 >= 3.5 推荐投递
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class EvaluationService {

    private final EvaluationMapper evaluationMapper;
    private final ArchetypeDetector archetypeDetector;
    private final ObjectMapper objectMapper = new ObjectMapper();

    /** 默认评分阈值 */
    public static final double DEFAULT_THRESHOLD = 3.5;

    /** 评分维度权重 */
    private static final Map<String, Double> WEIGHTS = Map.of(
        "A", 0.20,  // 角色匹配
        "B", 0.20,  // 能力匹配
        "C", 0.15,  // 薪酬合理
        "D", 0.10,  // 公司文化
        "E", 0.15,  // 成长空间
        "F", 0.10,  // 面试准备
        "G", 0.10   // 岗位合法性
    );

    /**
     * 对岗位执行完整的 A-G 评估
     */
    public EvaluationResult evaluate(JobInfo job, CandidateProfile profile) {
        EvaluationResult result = new EvaluationResult();
        result.encryptId = job.getEncryptId();
        result.platform = job.getPlatform();
        result.companyName = job.getCompanyName();
        result.jobName = job.getJobName();

        // A - 角色概要与类型检测
        result.scoreA = evaluateRoleSummary(job);
        result.archetype = archetypeDetector.detect(job.getJobName(), job.getJobDescription()).getCode();

        // B - 能力匹配度
        result.scoreB = evaluateSkillMatch(job, profile);

        // C - 薪酬合理性
        result.scoreC = evaluateCompensation(job, profile);

        // D - 公司文化与稳定性
        result.scoreD = evaluateCompanyFit(job);

        // E - 成长与发展空间
        result.scoreE = evaluateGrowth(job);

        // F - 面试准备评估
        result.scoreF = evaluateInterviewReadiness(job);

        // G - 岗位合法性（识别幽灵职位）
        result.scoreG = evaluateLegitimacy(job);

        // 计算加权总分
        result.totalScore = calculateWeightedScore(result);
        result.totalScore = Math.round(result.totalScore * 10.0) / 10.0;

        // 生成评估 JSON
        result.evaluationJson = buildEvaluationJson(result, job);

        // 持久化
        saveEvaluation(result, job);

        log.info("A-G 评估完成: {}/{} 原型={} 总分={}",
            job.getCompanyName(), job.getJobName(), result.archetype, result.totalScore);

        return result;
    }

    /**
     * A - 角色概要评估
     */
    private int evaluateRoleSummary(JobInfo job) {
        int score = 3; // 基础分
        String text = (job.getJobName() + " " + (job.getJobDescription() != null ? job.getJobDescription() : "")).toLowerCase();

        // 岗位名称清晰度
        if (job.getJobName() != null && job.getJobName().length() >= 4) score++;
        if (job.getJobName() != null && job.getJobName().length() < 3) score--;

        // JD 描述完整性
        if (job.getJobDescription() != null && job.getJobDescription().length() > 100) score++;
        if (job.getJobDescription() != null && job.getJobDescription().length() > 500) score++;

        // 明确的方向描述
        if (text.contains("职责") || text.contains("岗位职责") || text.contains("responsibility")) score++;
        if (text.contains("要求") || text.contains("任职资格") || text.contains("requirement")) score++;

        return clamp(score);
    }

    /**
     * B - 能力匹配度评估
     */
    private int evaluateSkillMatch(JobInfo job, CandidateProfile profile) {
        int score = 3;
        if (profile == null) return score;

        String jd = (job.getJobDescription() != null ? job.getJobDescription() : "").toLowerCase();
        String skills = (profile.getSkills() != null ? profile.getSkills() : "").toLowerCase();
        String title = (job.getJobName() != null ? job.getJobName() : "").toLowerCase();

        // 关键词匹配
        String[] skillList = skills.split("[,，、]");
        int matchCount = 0;
        for (String skill : skillList) {
            skill = skill.trim();
            if (skill.isEmpty()) continue;
            if (jd.contains(skill) || title.contains(skill)) matchCount++;
        }

        double matchRate = skillList.length > 0 ? (double) matchCount / skillList.length : 0;
        if (matchRate >= 0.5) score += 2;
        else if (matchRate >= 0.3) score += 1;

        // 经验年限匹配
        if (profile.getExperienceYears() > 0 && job.getExperienceRequired() > 0) {
            int diff = profile.getExperienceYears() - job.getExperienceRequired();
            if (diff >= 0 && diff <= 3) score++;
            if (diff < -2) score -= 2; // 经验不足
        }

        return clamp(score);
    }

    /**
     * C - 薪酬合理性评估
     */
    private int evaluateCompensation(JobInfo job, CandidateProfile profile) {
        int score = 3;

        // 解析薪资
        double[] salaryRange = parseSalary(job.getSalary());
        if (salaryRange == null) return 3; // 无法解析

        double minSalary = salaryRange[0];
        double maxSalary = salaryRange[1];
        double avgSalary = (minSalary + maxSalary) / 2;

        // 与期望薪资对比
        if (profile != null && profile.getExpectedSalaryMin() > 0) {
            if (maxSalary >= profile.getExpectedSalaryMin()) {
                score += 2;
                if (avgSalary >= profile.getExpectedSalaryMin() * 1.2) score++;
            } else {
                score -= 2;
            }
        }

        // 薪资区间合理性
        if (maxSalary > 0 && minSalary > 0) {
            double ratio = maxSalary / minSalary;
            if (ratio >= 1.3 && ratio <= 3.0) score++; // 合理区间
            if (ratio > 5.0) score--; // 区间过大不靠谱
        }

        // 有明确薪资
        if (job.getSalary() != null && !job.getSalary().isEmpty()) score++;

        return clamp(score);
    }

    /**
     * D - 公司文化与稳定性
     */
    private int evaluateCompanyFit(JobInfo job) {
        int score = 3;

        // 公司规模
        String scale = job.getCompanyScale() != null ? job.getCompanyScale() : "";
        if (scale.contains("上市") || scale.contains("500")) score++;
        if (scale.contains("少于") || scale.contains("0-20")) score--;

        // 融资阶段
        String stage = job.getFinancingStage() != null ? job.getFinancingStage() : "";
        if (stage.contains("上市") || stage.contains("D轮") || stage.contains("C轮")) score++;
        if (stage.contains("未融资") || stage.contains("天使")) score--;

        // 行业
        String industry = job.getIndustry() != null ? job.getIndustry() : "";
        if (!industry.isEmpty() && !industry.contains("其他")) score++;

        // HR 活跃度
        String hrStatus = job.getHrActiveStatus() != null ? job.getHrActiveStatus() : "";
        if (hrStatus.contains("在线") || hrStatus.contains("今日")) score++;
        if (hrStatus.contains("半年前") || hrStatus.contains("已离职")) score -= 2;

        return clamp(score);
    }

    /**
     * E - 成长与发展空间
     */
    private int evaluateGrowth(JobInfo job) {
        int score = 3;

        String text = (job.getJobDescription() != null ? job.getJobDescription() : "").toLowerCase();

        // 有明确的成长描述
        if (text.contains("晋升") || text.contains("成长") || text.contains("培养") || text.contains("培训")) score++;
        if (text.contains("期权") || text.contains("股权") || text.contains("股票")) score++;
        if (text.contains("年终") || text.contains("奖金") || text.contains("补贴")) score++;

        // 技术/业务挑战
        if (text.contains("挑战") || text.contains("核心") || text.contains("主导")) score++;
        if (text.contains("高并发") || text.contains("海量") || text.contains("大流量")) score++;

        return clamp(score);
    }

    /**
     * F - 面试准备评估
     */
    private int evaluateInterviewReadiness(JobInfo job) {
        int score = 3;

        String text = (job.getJobDescription() != null ? job.getJobDescription() : "").toLowerCase();

        // JD 有明确的技术栈要求 -> 可准备
        if (text.contains("Java") || text.contains("Python") || text.contains("Go") ||
            text.contains("React") || text.contains("Vue") || text.contains("Spring")) score++;

        // 有明确的业务描述 -> 好准备
        if (text.length() > 300) score++;
        if (text.contains("项目") || text.contains("业务") || text.contains("产品")) score++;

        // 信息不足
        if (job.getJobDescription() == null || job.getJobDescription().length() < 50) score -= 2;

        return clamp(score);
    }

    /**
     * G - 岗位合法性评估（幽灵职位识别）
     */
    private int evaluateLegitimacy(JobInfo job) {
        int score = 4; // 默认较高

        // HR 活跃度信号
        String hrStatus = job.getHrActiveStatus() != null ? job.getHrActiveStatus() : "";
        if (hrStatus.contains("半年前") || hrStatus.contains("已离职")) score -= 2;
        if (hrStatus.contains("今日") || hrStatus.contains("刚刚") || hrStatus.contains("在线")) score++;

        // 公司信息完整性
        if (job.getCompanyName() == null || job.getCompanyName().isEmpty()) score -= 2;
        if (job.getCompanyScale() == null || job.getCompanyScale().isEmpty()) score--;

        // 薪资信息
        if (job.getSalary() == null || job.getSalary().isEmpty()) score--;

        // 招聘状态
        String recruitStatus = job.getRecruitmentStatus() != null ? job.getRecruitmentStatus() : "";
        if (recruitStatus.contains("停止") || recruitStatus.contains("关闭")) score -= 2;

        // JD 质量
        if (job.getJobDescription() != null && job.getJobDescription().length() > 200) score++;
        if (job.getJobDescription() != null && job.getJobDescription().length() < 30) score -= 2;

        return clamp(score);
    }

    /**
     * 加权计算总分
     */
    private double calculateWeightedScore(EvaluationResult result) {
        double total = 0;
        total += result.scoreA * WEIGHTS.get("A");
        total += result.scoreB * WEIGHTS.get("B");
        total += result.scoreC * WEIGHTS.get("C");
        total += result.scoreD * WEIGHTS.get("D");
        total += result.scoreE * WEIGHTS.get("E");
        total += result.scoreF * WEIGHTS.get("F");
        total += result.scoreG * WEIGHTS.get("G");
        return total;
    }

    /**
     * 构建评估结果 JSON
     */
    private String buildEvaluationJson(EvaluationResult result, JobInfo job) {
        try {
            Map<String, Object> json = new LinkedHashMap<>();
            json.put("archetype", result.archetype);
            json.put("scores", Map.of(
                "A", result.scoreA,
                "B", result.scoreB,
                "C", result.scoreC,
                "D", result.scoreD,
                "E", result.scoreE,
                "F", result.scoreF,
                "G", result.scoreG
            ));
            json.put("totalScore", result.totalScore);
            json.put("threshold", DEFAULT_THRESHOLD);
            json.put("weights", WEIGHTS);
            json.put("recommendation", result.totalScore >= DEFAULT_THRESHOLD ? "投递" : "跳过");
            json.put("evaluatedAt", LocalDateTime.now().toString());
            return objectMapper.writeValueAsString(json);
        } catch (JsonProcessingException e) {
            log.warn("构建评估 JSON 失败", e);
            return "{}";
        }
    }

    /**
     * 持久化评估结果
     */
    private void saveEvaluation(EvaluationResult result, JobInfo job) {
        try {
            EvaluationEntity entity = new EvaluationEntity();
            entity.setEncryptId(result.encryptId);
            entity.setPlatform(result.platform);
            entity.setCompanyName(result.companyName);
            entity.setJobName(result.jobName);
            entity.setArchetype(result.archetype);
            entity.setScoreA(result.scoreA);
            entity.setScoreB(result.scoreB);
            entity.setScoreC(result.scoreC);
            entity.setScoreD(result.scoreD);
            entity.setScoreE(result.scoreE);
            entity.setScoreF(result.scoreF);
            entity.setScoreG(result.scoreG);
            entity.setTotalScore(result.totalScore);
            entity.setEvaluationJson(result.evaluationJson);
            entity.setCreatedAt(LocalDateTime.now());
            evaluationMapper.insert(entity);
        } catch (Exception e) {
            log.warn("保存评估结果失败: {}", e.getMessage());
        }
    }

    /**
     * 将分数限制在 1-5 范围
     */
    private int clamp(int score) {
        return Math.max(1, Math.min(5, score));
    }

    /**
     * 解析薪资字符串
     * 支持: "20K-40K", "15k-25k·14薪", "30-50K·16薪", "200-300/天"
     */
    public static double[] parseSalary(String salaryStr) {
        if (salaryStr == null || salaryStr.isEmpty()) return null;
        try {
            String s = salaryStr.replaceAll("·.*$", "").replaceAll("\\*.*$", "").trim();
            // 支持 "20K-40K", "15k-25k·14薪", "30-50K·16薪", "200-300/天"
            Pattern p = Pattern.compile("(\\d+(\\.\\d+)?)\\s*[Kk]?\\s*[-~到]\\s*(\\d+(\\.\\d+)?)\\s*[Kk]?");
            Matcher m = p.matcher(s);
            if (m.find()) {
                double min = Double.parseDouble(m.group(1));
                double max = Double.parseDouble(m.group(3));
                boolean isK = salaryStr.toLowerCase().contains("k");
                if (isK) {
                    min *= 1000;
                    max *= 1000;
                }
                // 判断是月薪还是日薪
                if (salaryStr.contains("/天") || salaryStr.contains("/day")) {
                    min *= 21; // 按21个工作日估算月薪
                    max *= 21;
                }
                return new double[]{min, max};
            }
        } catch (Exception e) {
            log.warn("薪资解析失败: {}", salaryStr);
        }
        return null;
    }

    public boolean shouldDeliver(JobInfo job, CandidateProfile profile, double threshold) {
        EvaluationResult result = evaluate(job, profile);
        return result.totalScore >= threshold;
    }

    public boolean shouldDeliver(JobInfo job, CandidateProfile profile) {
        return shouldDeliver(job, profile, DEFAULT_THRESHOLD);
    }

    /**
     * Job 信息数据传输到评估器
     */
    @Data
    public static class JobInfo {
        private String encryptId;
        private String platform = "boss";
        private String companyName;
        private String jobName;
        private String salary;
        private String jobDescription;
        private String companyScale;
        private String financingStage;
        private String industry;
        private String hrActiveStatus;
        private String recruitmentStatus;
        private int experienceRequired;

        public JobInfo() {}

        public JobInfo(String encryptId, String companyName, String jobName, String salary, String jobDescription) {
            this.encryptId = encryptId;
            this.companyName = companyName;
            this.jobName = jobName;
            this.salary = salary;
            this.jobDescription = jobDescription;
        }
    }

    /**
     * 用户画像
     */
    @Data
    public static class CandidateProfile {
        private String skills;
        private int experienceYears;
        private double expectedSalaryMin;
        private double expectedSalaryMax;
    }

    /**
     * A-G 评估结果
     */
    @Data
    public static class EvaluationResult {
        private String encryptId;
        private String platform;
        private String companyName;
        private String jobName;
        private String archetype;
        private int scoreA;
        private int scoreB;
        private int scoreC;
        private int scoreD;
        private int scoreE;
        private int scoreF;
        private int scoreG;
        private double totalScore;
        private String evaluationJson;
    }
}
