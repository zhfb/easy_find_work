package com.efw.application.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.tika.Tika;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * 简历生成服务
 * 三选一：手动上传 / AI 自动生成 / PDF 转图片
 * 支持自进化：每 10 份简历自动内部评审
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ResumeService {

    private final AiService aiService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    /** 简历计数器文件路径 */
    private static final String COUNTER_FILE = "output/resumes/resume-counter.txt";
    /** 简历输出目录 */
    private static final String OUTPUT_DIR = "output/resumes";
    /** 评审输出目录 */
    private static final String REVIEW_DIR = "output/resumes/reviews";
    /** 默认手动上传简历路径 */
    private static final String MANUAL_RESUME_PATH = "src/main/resources/resume_custom.jpg";
    /** 上传简历存储目录 */
    private static final String UPLOAD_DIR = "output/resumes/uploaded";
    /** 每 N 份简历触发一次评审 */
    private static final int REVIEW_INTERVAL = 10;

    private final Tika tika = new Tika();

    /**
     * 获取项目根目录的绝对路径
     */
    private String getProjectRoot() {
        return System.getProperty("user.dir", ".");
    }

    /**
     * 获取输出目录的绝对路径
     */
    private Path getUploadDir() {
        Path dir = Paths.get(getProjectRoot(), UPLOAD_DIR);
        try {
            Files.createDirectories(dir);
        } catch (IOException e) {
            log.warn("创建上传目录失败: {}", e.getMessage());
        }
        return dir;
    }

    private final AtomicInteger resumeCounter = new AtomicInteger(loadCounter());

    /**
     * 生成简历（根据来源配置）
     */
    public ResumeResult generateResume(ResumeRequest request) {
        return switch (request.getSource()) {
            case "manual" -> useManualResume(request);
            case "ai" -> generateAiResume(request);
            default -> useManualResume(request);
        };
    }

    /**
     * 使用手动上传的简历
     */
    private ResumeResult useManualResume(ResumeRequest request) {
        Path path = Paths.get(MANUAL_RESUME_PATH);
        if (Files.exists(path)) {
            log.info("使用手动上传简历: {}", MANUAL_RESUME_PATH);
            return new ResumeResult("manual", MANUAL_RESUME_PATH, null);
        }
        log.warn("手动简历不存在: {}", MANUAL_RESUME_PATH);
        return new ResumeResult("manual", null, "手动简历文件不存在，请上传");
    }

    /**
     * AI 自动生成简历
     * 根据 JD + 个人信息生成 HTML 简历
     */
    private ResumeResult generateAiResume(ResumeRequest request) {
        try {
            int counter = resumeCounter.incrementAndGet();
            saveCounter(counter);

            String fileName = String.format("%03d-%s-%s.html",
                counter, sanitizeFileName(request.getCompanyName()), LocalDate.now().format(DateTimeFormatter.BASIC_ISO_DATE));

            // 确保输出目录存在
            Files.createDirectories(Paths.get(OUTPUT_DIR));

            // 使用 AI 生成简历内容
            String resumeHtml = buildResumeHtml(request);

            Path outputPath = Paths.get(OUTPUT_DIR, fileName);
            Files.writeString(outputPath, resumeHtml);

            log.info("AI 简历已生成: {}", outputPath);

            // 检查是否需要触发评审
            if (counter % REVIEW_INTERVAL == 0) {
                triggerReview(counter, request);
            }

            return new ResumeResult("ai", outputPath.toString(), null);
        } catch (Exception e) {
            log.error("AI 简历生成失败", e);
            return new ResumeResult("ai", null, "生成失败: " + e.getMessage());
        }
    }

    /**
     * 构建简历 HTML
     */
    private String buildResumeHtml(ResumeRequest request) {
        String jd = request.getJobDescription() != null ? request.getJobDescription() : "";
        String skills = request.getSkills() != null ? request.getSkills() : "";
        String experience = request.getExperience() != null ? request.getExperience() : "";

        // 从 JD 提取关键词并注入
        List<String> jdKeywords = extractJdKeywords(jd);

        return String.format("""
            <!DOCTYPE html>
            <html lang="zh-CN">
            <head>
            <meta charset="UTF-8">
            <title>%s - %s</title>
            <style>
                @page { margin: 0.6in; }
                body { font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif; font-size: 11pt; color: #333; line-height: 1.5; }
                .header { text-align: center; margin-bottom: 20px; }
                .header h1 { font-size: 22pt; margin: 0; color: #1a1a2e; }
                .header .subtitle { color: #666; font-size: 10pt; margin-top: 4px; }
                .section { margin-bottom: 16px; }
                .section-title { font-size: 12pt; font-weight: bold; color: #1a1a2e; border-bottom: 2px solid #2563eb; padding-bottom: 4px; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.06em; }
                .skills-grid { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
                .skill-tag { background: #eff6ff; color: #1e40af; padding: 2px 10px; border-radius: 12px; font-size: 9pt; border: 1px solid #bfdbfe; }
                .experience-item { margin-bottom: 12px; }
                .experience-item h3 { font-size: 11pt; margin: 0; color: #1a1a2e; }
                .experience-item .meta { font-size: 9pt; color: #666; margin: 2px 0 4px; }
                .experience-item ul { margin: 4px 0; padding-left: 18px; }
                .experience-item li { margin-bottom: 2px; font-size: 10pt; }
                .project-item { margin-bottom: 10px; }
                .project-item h3 { font-size: 11pt; margin: 0; color: #1a1a2e; }
                .project-item .meta { font-size: 9pt; color: #666; }
                .education-item { margin-bottom: 8px; }
                .education-item h3 { font-size: 11pt; margin: 0; }
                .education-item .meta { font-size: 9pt; color: #666; }
            </style>
            </head>
            <body>
            <div class="header">
                <h1>%s</h1>
                <div class="subtitle">%s | %s | %s</div>
            </div>

            <div class="section">
                <div class="section-title">Professional Summary</div>
                <p>%s</p>
            </div>

            <div class="section">
                <div class="section-title">Core Competencies</div>
                <div class="skills-grid">
                    %s
                </div>
            </div>

            <div class="section">
                <div class="section-title">Work Experience</div>
                %s
            </div>

            <div class="section">
                <div class="section-title">Education</div>
                <div class="education-item">
                    <h3>%%E5%%AD%%A6%%E5%%8E%%86%%E4%%BF%%A1%%E6%%81%%AF</h3>
                </div>
            </div>
            </body>
            </html>
            """,
            request.getCompanyName(), request.getJobName(),
            request.getCandidateName() != null ? request.getCandidateName() : "候选人",
            request.getTargetRole() != null ? request.getTargetRole() : "",
            request.getLocation() != null ? request.getLocation() : "",
            request.getEmail() != null ? request.getEmail() : "",
            buildSummary(request, jdKeywords),
            buildSkillTags(jdKeywords, skills),
            buildExperienceHtml(experience)
        );
    }

    private String buildSummary(ResumeRequest request, List<String> keywords) {
        StringBuilder sb = new StringBuilder();
        sb.append("经验丰富的 ");
        if (request.getTargetRole() != null) sb.append(request.getTargetRole());
        sb.append(" 专业人员，");
        if (!keywords.isEmpty()) {
            sb.append("精通 ");
            sb.append(String.join("、", keywords.subList(0, Math.min(5, keywords.size()))));
            sb.append(" 等技术栈。");
        }
        return sb.toString();
    }

    private String buildSkillTags(List<String> jdKeywords, String skills) {
        Set<String> allSkills = new LinkedHashSet<>();
        if (skills != null && !skills.isEmpty()) {
            for (String s : skills.split("[,，、]")) {
                String trimmed = s.trim();
                if (!trimmed.isEmpty()) allSkills.add(trimmed);
            }
        }
        allSkills.addAll(jdKeywords);

        StringBuilder sb = new StringBuilder();
        for (String skill : allSkills) {
            if (sb.length() > 80) break;
            sb.append("<span class=\"skill-tag\">").append(escapeHtml(skill)).append("</span>");
        }
        return sb.toString();
    }

    private String buildExperienceHtml(String experience) {
        if (experience == null || experience.isBlank()) {
            return "<p class=\"text-gray-500\">暂无工作经历信息</p>";
        }
        StringBuilder sb = new StringBuilder();
        String[] lines = experience.split("\n");
        boolean inList = false;
        for (String line : lines) {
            line = line.trim();
            if (line.isEmpty()) continue;
            if (line.startsWith("- ") || line.startsWith("* ")) {
                if (!inList) { sb.append("<ul>"); inList = true; }
                sb.append("<li>").append(escapeHtml(line.substring(2))).append("</li>");
            } else {
                if (inList) { sb.append("</ul>"); inList = false; }
                if (line.contains("公司") || line.contains("有限公司") || line.matches(".*\\d{4}.*")) {
                    sb.append("<div class=\"experience-item\"><h3>").append(escapeHtml(line)).append("</h3></div>");
                } else {
                    sb.append("<p>").append(escapeHtml(line)).append("</p>");
                }
            }
        }
        if (inList) sb.append("</ul>");
        return sb.toString();
    }

    /**
     * 从 JD 提取关键词
     */
    private List<String> extractJdKeywords(String jd) {
        List<String> keywords = new ArrayList<>();
        String[] techTerms = {
            "Java", "Python", "Go", "Golang", "Spring", "Spring Boot", "微服务", "分布式",
            "Redis", "MySQL", "Kafka", "Docker", "Kubernetes", "K8s", "React", "Vue",
            "TypeScript", "JavaScript", "Node", "Flutter", "大数据", "Spark", "Flink",
            "DevOps", "CI/CD", "AWS", "Azure", "Linux", "API", "REST", "gRPC",
            "消息队列", "MQ", "Elasticsearch", "MongoDB", "设计模式", "架构设计"
        };
        for (String term : techTerms) {
            if (jd.contains(term)) {
                keywords.add(term);
            }
        }
        return keywords;
    }

    /**
     * 触发简历评审（自进化）
     */
    private void triggerReview(int counter, ResumeRequest request) {
        try {
            Files.createDirectories(Paths.get(REVIEW_DIR));
            String reviewFile = String.format("review-%03d-%s.md", counter, LocalDate.now());
            String content = String.format("""
                # 简历内部评审报告

                **生成时间**: %s
                **当前简历数**: %s
                **最近岗位**: %s (%s)

                ## 评审维度

                1. **关键词注入效果**: 最近 10 份简历的 JD 关键词提取覆盖度
                2. **模板排版质量**: HTML 渲染检查
                3. **回复率关联**: 已投递岗位的回复率与简历质量关联分析

                ## 改进建议

                - 根据目标岗位类型动态调整技能标签排序
                - 优化专业技能描述的 JD 关键词密度
                - 检查模板在不同浏览器/ATS 中的兼容性

                ## 后续操作

                - [ ] 查看已生成的简历文件
                - [ ] 根据评审结果调整简历策略
                - [ ] 更新 keywords injection 规则
                """,
                LocalDateTime.now(), counter,
                request.getCompanyName(), request.getJobName()
            );
            Files.writeString(Paths.get(REVIEW_DIR, reviewFile), content);
            log.info("简历评审报告已生成: {}", reviewFile);
        } catch (IOException e) {
            log.warn("生成评审报告失败", e);
        }
    }

    /**
     * 获取简历列表
     */
    public List<Map<String, Object>> getResumeList() {
        List<Map<String, Object>> list = new ArrayList<>();
        try {
            Path dir = Paths.get(OUTPUT_DIR);
            if (Files.exists(dir)) {
                Files.list(dir)
                    .filter(p -> p.toString().endsWith(".html") || p.toString().endsWith(".jpg"))
                    .sorted()
                    .forEach(p -> {
                        Map<String, Object> item = new HashMap<>();
                        item.put("name", p.getFileName().toString());
                        item.put("path", p.toString());
                        item.put("size", p.toFile().length());
                        item.put("lastModified", p.toFile().lastModified());
                        list.add(item);
                    });
            }
        } catch (IOException e) {
            log.warn("获取简历列表失败", e);
        }
        return list;
    }

    /**
     * 获取评审报告列表
     */
    public List<String> getReviewList() {
        List<String> list = new ArrayList<>();
        try {
            Path dir = Paths.get(REVIEW_DIR);
            if (Files.exists(dir)) {
                Files.list(dir)
                    .filter(p -> p.toString().endsWith(".md"))
                    .sorted()
                    .forEach(p -> list.add(p.getFileName().toString()));
            }
        } catch (IOException e) {
            log.warn("获取评审报告列表失败", e);
        }
        return list;
    }

    private int loadCounter() {
        try {
            Path path = Paths.get(COUNTER_FILE);
            if (Files.exists(path)) {
                return Integer.parseInt(Files.readString(path).trim());
            }
        } catch (Exception e) {
            log.warn("加载简历计数器失败", e);
        }
        return 0;
    }

    private void saveCounter(int count) {
        try {
            Files.createDirectories(Paths.get(OUTPUT_DIR));
            Files.writeString(Paths.get(COUNTER_FILE), String.valueOf(count));
        } catch (IOException e) {
            log.warn("保存简历计数器失败", e);
        }
    }

    private String sanitizeFileName(String name) {
        return name != null ? name.replaceAll("[\\\\/:*?\"<>|]", "_").replaceAll("\\s+", "_") : "unknown";
    }

    private String escapeHtml(String text) {
        return text != null ? text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\"", "&quot;") : "";
    }

    // ================= 简历上传 & AI 分析 =================

    /**
     * 上传并保存简历文件，提取文本内容
     */
    public ResumeUploadResult uploadResume(MultipartFile file) {
        try {
            Path uploadDir = getUploadDir();
            String originalName = file.getOriginalFilename();
            if (originalName == null || originalName.isBlank()) {
                originalName = "resume_" + System.currentTimeMillis();
            }
            // 安全文件名
            String safeName = System.currentTimeMillis() + "_" + sanitizeFileName(originalName);
            Path targetPath = uploadDir.resolve(safeName);
            file.transferTo(targetPath.toFile());

            // 提取文本
            String extractedText = tika.parseToString(targetPath.toFile());
            log.info("简历上传成功: {}, 提取文本长度: {}", safeName, extractedText.length());

            return new ResumeUploadResult(true, safeName, targetPath.toString(), extractedText, null);
        } catch (Exception e) {
            log.error("简历上传/解析失败", e);
            return new ResumeUploadResult(false, null, null, null, "解析失败: " + e.getMessage());
        }
    }

    /**
     * 使用 AI 分析简历文本，提取技能、经验、教育等信息
     */
    public ResumeAnalysisResult analyzeResume(String extractedText) {
        try {
            String prompt = """
                你是一个专业的简历解析助手。请分析以下简历内容，提取关键信息，以JSON格式返回。
                必须包含以下字段：
                - skills: 技能列表（数组），提取所有技术/软技能
                - experience: 工作经历总结（字符串）
                - education: 教育背景（字符串）
                - yearsOfExperience: 工作年限（数字，如无法确定则填0）
                - targetRoles: 目标岗位（数组）

                简历内容：
                """ + extractedText;

            String aiResponse = aiService.sendRequest(prompt);

            // 尝试从 AI 响应中提取 JSON
            String jsonStr = aiResponse;
            int jsonStart = aiResponse.indexOf('{');
            int jsonEnd = aiResponse.lastIndexOf('}');
            if (jsonStart >= 0 && jsonEnd > jsonStart) {
                jsonStr = aiResponse.substring(jsonStart, jsonEnd + 1);
            }

            Map<String, Object> parsed = objectMapper.readValue(jsonStr, Map.class);
            String skills = parsed.containsKey("skills") ? String.join(", ", (List<String>) parsed.get("skills")) : "";
            String experience = parsed.getOrDefault("experience", "").toString();
            String education = parsed.getOrDefault("education", "").toString();
            int years = parsed.containsKey("yearsOfExperience") ? ((Number) parsed.get("yearsOfExperience")).intValue() : 0;
            Object targetRolesObj = parsed.get("targetRoles");
            String targetRoles = targetRolesObj instanceof List ? String.join(", ", (List<String>) targetRolesObj) : "";

            // 自动保存技能介绍到 ai_config
            String skillIntro = skills.isEmpty() ? extractedText.substring(0, Math.min(500, extractedText.length())) : skills;
            try {
                var aiEntity = aiService.getAiConfig();
                String currentIntro = aiEntity.getIntroduce();
                // 只在当前技能介绍为空或为默认值时覆盖
                if (currentIntro == null || currentIntro.isBlank() || currentIntro.contains("请在此填写")) {
                    aiService.saveOrUpdateAiConfig(skillIntro, aiEntity.getPrompt());
                    log.info("已自动更新 AI 配置的技能介绍");
                }
            } catch (Exception e) {
                log.warn("自动更新 AI 配置失败: {}", e.getMessage());
            }

            return new ResumeAnalysisResult(true, skills, experience, education, years, targetRoles, null);
        } catch (Exception e) {
            log.error("AI 简历分析失败", e);
            return new ResumeAnalysisResult(false, "", "", "", 0, "", "分析失败: " + e.getMessage());
        }
    }

    @Data
    @AllArgsConstructor
    public static class ResumeUploadResult {
        private boolean success;
        private String fileName;
        private String filePath;
        private String extractedText;
        private String error;
    }

    @Data
    @AllArgsConstructor
    public static class ResumeAnalysisResult {
        private boolean success;
        private String skills;
        private String experience;
        private String education;
        private int yearsOfExperience;
        private String targetRoles;
        private String error;
    }

    @Data
    public static class ResumeRequest {
        private String source = "manual"; // manual | ai
        private String companyName;
        private String jobName;
        private String jobDescription;
        private String candidateName;
        private String targetRole;
        private String location;
        private String email;
        private String phone;
        private String skills;
        private String experience;
        private String education;
        private String projects;
    }

    @Data
    public static class ResumeResult {
        private final String source;
        private final String path;
        private final String error;

        public boolean isSuccess() { return path != null && error == null; }
    }
}
