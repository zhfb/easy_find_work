package com.efw.application.service;

import lombok.Data;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.time.LocalDateTime;
import java.util.*;

/**
 * 面试准备服务
 * 基于 Career-Ops / EFW 的 STAR+L 故事库和面试准备模式
 */
@Slf4j
@Service
public class InterviewPrepService {

    private static final String STORY_BANK_FILE = "interview-prep/story-bank.md";
    private static final String QUESTIONS_FILE = "interview-prep/chinese-questions.yml";
    private static final String PREP_DIR = "interview-prep";

    /** 中文面试常见问题 */
    private static final List<ChineseQuestion> DEFAULT_QUESTIONS = Arrays.asList(
        new ChineseQuestion("自我介绍", "behavioral", "请简单介绍一下你自己"),
        new ChineseQuestion("离职原因", "behavioral", "你为什么离开上一家公司？"),
        new ChineseQuestion("期望薪资", "compensation", "你的期望薪资是多少？"),
        new ChineseQuestion("职业规划", "career", "你未来3-5年的职业规划是什么？"),
        new ChineseQuestion("优缺点", "behavioral", "你最大的优点和缺点是什么？"),
        new ChineseQuestion("项目经验", "technical", "请分享一个你最满意的项目"),
        new ChineseQuestion("团队冲突", "behavioral", "你如何处理团队中的冲突？"),
        new ChineseQuestion("压力处理", "behavioral", "你在压力最大的时候是如何应对的？"),
        new ChineseQuestion("失败经历", "behavioral", "请分享一次失败的经历以及你学到了什么"),
        new ChineseQuestion("为什么选我们", "motivation", "你为什么选择我们公司？"),
        new ChineseQuestion("技术挑战", "technical", "你遇到过的最大技术挑战是什么？"),
        new ChineseQuestion("学习能力", "growth", "你最近学习了什么新技术？"),
        new ChineseQuestion("加班看法", "cultural", "你对加班怎么看？"),
        new ChineseQuestion("空窗期", "behavioral", "你简历上的空窗期在做什么？"),
        new ChineseQuestion("管理风格", "leadership", "请描述你的管理风格")
    );

    /**
     * 添加 STAR+L 故事到故事库
     */
    public void addStory(StoryEntry entry) {
        try {
            Files.createDirectories(Paths.get(PREP_DIR));
            String storyText = formatStory(entry);
            Files.writeString(Paths.get(STORY_BANK_FILE), storyText, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
            log.info("故事已添加到故事库: {}", entry.getTitle());
        } catch (IOException e) {
            log.warn("添加故事到故事库失败", e);
        }
    }

    /**
     * 获取所有故事
     */
    public List<StoryEntry> getStories() {
        List<StoryEntry> stories = new ArrayList<>();
        try {
            Path path = Paths.get(STORY_BANK_FILE);
            if (Files.exists(path)) {
                String content = Files.readString(path);
                // 简单解析 Markdown 格式的故事
                String[] blocks = content.split("(?=### )");
                for (String block : blocks) {
                    if (block.trim().isEmpty()) continue;
                    StoryEntry entry = parseStoryBlock(block);
                    if (entry != null) stories.add(entry);
                }
            }
        } catch (IOException e) {
            log.warn("读取故事库失败", e);
        }
        return stories;
    }

    /**
     * 获取所有面试问题
     */
    public List<ChineseQuestion> getQuestions() {
        return DEFAULT_QUESTIONS;
    }

    /**
     * 按分类获取问题
     */
    public List<ChineseQuestion> getQuestionsByCategory(String category) {
        return DEFAULT_QUESTIONS.stream()
            .filter(q -> q.getCategory().equals(category))
            .toList();
    }

    /**
     * 生成面试准备文档
     */
    public String generatePrepDocument(String companyName, String jobName, String jd) {
        try {
            Files.createDirectories(Paths.get(PREP_DIR));
            String fileName = String.format("%s-%s-prep.md",
                companyName.replaceAll("[\\\\/:*?\"<>|]", "_"),
                jobName.replaceAll("[\\\\/:*?\"<>|]", "_"));

            StringBuilder doc = new StringBuilder();
            doc.append(String.format("# 面试准备: %s - %s\n\n", companyName, jobName));
            doc.append(String.format("**生成时间**: %s\n\n", LocalDateTime.now()));
            doc.append("## 岗位信息\n\n");
            doc.append(String.format("- 公司: %s\n", companyName));
            doc.append(String.format("- 岗位: %s\n", jobName));
            doc.append("\n## 可能的面试问题\n\n");

            // 根据 JD 相关内容推荐问题
            String jdLower = jd != null ? jd.toLowerCase() : "";
            for (ChineseQuestion q : DEFAULT_QUESTIONS) {
                doc.append(String.format("- %s (%s)\n", q.getQuestion(), q.getCategory()));
            }

            doc.append("\n## 故事库匹配\n\n");
            List<StoryEntry> stories = getStories();
            if (stories.isEmpty()) {
                doc.append("暂无故事，请先添加 STAR+L 故事。\n");
            } else {
                for (StoryEntry story : stories) {
                    doc.append(String.format("- **%s**: %s\n", story.getTitle(), story.getSituation()));
                }
            }

            doc.append("\n## 准备清单\n\n");
            doc.append("- [ ] 研究公司背景和产品\n");
            doc.append("- [ ] 准备自我介绍（1分钟/3分钟版本）\n");
            doc.append("- [ ] 准备 3-5 个 STAR 故事\n");
            doc.append("- [ ] 准备要问面试官的问题\n");
            doc.append("- [ ] 确认面试时间和形式\n");

            Files.writeString(Paths.get(PREP_DIR, fileName), doc.toString());
            log.info("面试准备文档已生成: {}", fileName);
            return fileName;

        } catch (IOException e) {
            log.warn("生成面试准备文档失败", e);
            return null;
        }
    }

    /**
     * 根据岗位匹配推荐故事
     */
    public List<StoryEntry> recommendStories(String jd, int limit) {
        List<StoryEntry> allStories = getStories();
        if (allStories.isEmpty()) return Collections.emptyList();

        String jdLower = jd != null ? jd.toLowerCase() : "";

        // 按匹配度排序
        return allStories.stream()
            .sorted((a, b) -> {
                int scoreA = countKeywordMatches(jdLower, a.getSkills());
                int scoreB = countKeywordMatches(jdLower, b.getSkills());
                return Integer.compare(scoreB, scoreA);
            })
            .limit(limit)
            .toList();
    }

    private int countKeywordMatches(String text, String skills) {
        if (text == null || skills == null) return 0;
        int count = 0;
        for (String skill : skills.split("[,，、]")) {
            if (text.contains(skill.trim().toLowerCase())) count++;
        }
        return count;
    }

    private String formatStory(StoryEntry entry) {
        return String.format("""

            ### %s
            **来源**: %s
            **S (Situation/情境)**: %s
            **T (Task/任务)**: %s
            **A (Action/行动)**: %s
            **R (Result/结果)**: %s
            **L (Learning/经验教训)**: %s
            **适用问题**: %s
            **技能标签**: %s

            """,
            entry.getTitle(),
            entry.getSource() != null ? entry.getSource() : "手动添加",
            entry.getSituation() != null ? entry.getSituation() : "",
            entry.getTask() != null ? entry.getTask() : "",
            entry.getAction() != null ? entry.getAction() : "",
            entry.getResult() != null ? entry.getResult() : "",
            entry.getLearning() != null ? entry.getLearning() : "",
            entry.getApplicableQuestions() != null ? entry.getApplicableQuestions() : "",
            entry.getSkills() != null ? entry.getSkills() : ""
        );
    }

    private StoryEntry parseStoryBlock(String block) {
        try {
            StoryEntry entry = new StoryEntry();
            String[] lines = block.split("\n");
            for (String line : lines) {
                if (line.startsWith("### ")) {
                    entry.setTitle(line.substring(4).trim());
                } else if (line.startsWith("**来源**")) {
                    entry.setSource(extractValue(line));
                } else if (line.startsWith("**S (Situation/情境)**") || line.contains("S (Situation")) {
                    entry.setSituation(extractValue(line));
                } else if (line.startsWith("**T (Task/任务)**") || line.contains("T (Task")) {
                    entry.setTask(extractValue(line));
                } else if (line.startsWith("**A (Action/行动)**") || line.contains("A (Action")) {
                    entry.setAction(extractValue(line));
                } else if (line.startsWith("**R (Result/结果)**") || line.contains("R (Result")) {
                    entry.setResult(extractValue(line));
                } else if (line.startsWith("**L (Learning/经验教训)**") || line.contains("L (Learning")) {
                    entry.setLearning(extractValue(line));
                } else if (line.startsWith("**适用问题**")) {
                    entry.setApplicableQuestions(extractValue(line));
                } else if (line.startsWith("**技能标签**")) {
                    entry.setSkills(extractValue(line));
                }
            }
            return entry.getTitle() != null ? entry : null;
        } catch (Exception e) {
            return null;
        }
    }

    private String extractValue(String line) {
        int colonIdx = line.indexOf(": ");
        if (colonIdx >= 0 && colonIdx + 2 < line.length()) {
            return line.substring(colonIdx + 2).trim();
        }
        return "";
    }

    @Data
    public static class StoryEntry {
        private String title;
        private String source;
        private String situation;  // 情境
        private String task;       // 任务
        private String action;     // 行动
        private String result;     // 结果
        private String learning;   // 经验教训
        private String applicableQuestions; // 适用面试问题
        private String skills;     // 技能标签
    }

    @Data
    public static class ChineseQuestion {
        private String question;
        private String category; // behavioral, technical, compensation, career, cultural, growth, leadership, motivation
        private String description;

        public ChineseQuestion() {}

        public ChineseQuestion(String question, String category, String description) {
            this.question = question;
            this.category = category;
            this.description = description;
        }
    }
}
