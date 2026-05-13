package com.efw.application.controller;

import com.efw.application.service.InterviewPrepService;
import com.efw.application.service.InterviewPrepService.ChineseQuestion;
import com.efw.application.service.InterviewPrepService.StoryEntry;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 面试准备控制器
 */
@Slf4j
@RestController
@RequestMapping("/api/interview")
@CrossOrigin(origins = "*")
@RequiredArgsConstructor
public class InterviewController {

    private final InterviewPrepService interviewPrepService;

    /**
     * 获取所有故事
     */
    @GetMapping("/stories")
    public ResponseEntity<Map<String, Object>> getStories() {
        List<StoryEntry> stories = interviewPrepService.getStories();
        return ResponseEntity.ok(Map.of("success", true, "stories", stories));
    }

    /**
     * 添加故事
     */
    @PostMapping("/stories")
    public ResponseEntity<Map<String, Object>> addStory(@RequestBody StoryEntry entry) {
        try {
            interviewPrepService.addStory(entry);
            return ResponseEntity.ok(Map.of("success", true, "message", "故事已添加"));
        } catch (Exception e) {
            log.error("添加故事失败", e);
            return ResponseEntity.internalServerError().body(Map.of("success", false, "message", e.getMessage()));
        }
    }

    /**
     * 获取所有面试问题
     */
    @GetMapping("/questions")
    public ResponseEntity<Map<String, Object>> getQuestions() {
        List<ChineseQuestion> questions = interviewPrepService.getQuestions();
        return ResponseEntity.ok(Map.of("success", true, "questions", questions));
    }

    /**
     * 按分类获取问题
     */
    @GetMapping("/questions/{category}")
    public ResponseEntity<Map<String, Object>> getQuestionsByCategory(@PathVariable String category) {
        List<ChineseQuestion> questions = interviewPrepService.getQuestionsByCategory(category);
        return ResponseEntity.ok(Map.of("success", true, "questions", questions));
    }

    /**
     * 生成面试准备文档
     */
    @PostMapping("/prepare")
    public ResponseEntity<Map<String, Object>> prepare(@RequestBody Map<String, String> body) {
        String companyName = body.get("companyName");
        String jobName = body.get("jobName");
        String jd = body.get("jd");

        if (companyName == null || jobName == null) {
            return ResponseEntity.badRequest().body(Map.of("success", false, "message", "companyName 和 jobName 不能为空"));
        }

        String fileName = interviewPrepService.generatePrepDocument(companyName, jobName, jd);
        if (fileName != null) {
            return ResponseEntity.ok(Map.of("success", true, "message", "面试准备文档已生成", "file", fileName));
        }
        return ResponseEntity.internalServerError().body(Map.of("success", false, "message", "生成失败"));
    }

    /**
     * 推荐故事
     */
    @PostMapping("/recommend-stories")
    public ResponseEntity<Map<String, Object>> recommendStories(@RequestBody Map<String, String> body) {
        String jd = body.getOrDefault("jd", "");
        int limit = Integer.parseInt(body.getOrDefault("limit", "6"));
        List<StoryEntry> stories = interviewPrepService.recommendStories(jd, limit);
        return ResponseEntity.ok(Map.of("success", true, "stories", stories));
    }
}
