package com.efw.application.controller;

import com.efw.application.service.EvaluationService;
import com.efw.application.service.EvaluationService.EvaluationResult;
import com.efw.application.service.EvaluationService.JobInfo;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * A-G 评估控制器
 */
@Slf4j
@RestController
@RequestMapping("/api/evaluation")
@CrossOrigin(origins = "*")
@RequiredArgsConstructor
public class EvaluationController {

    private final EvaluationService evaluationService;

    /**
     * 评估一个岗位
     */
    @PostMapping("/evaluate")
    public ResponseEntity<Map<String, Object>> evaluate(@RequestBody JobInfo jobInfo) {
        try {
            EvaluationResult result = evaluationService.evaluate(jobInfo, null);
            return ResponseEntity.ok(Map.of(
                "success", true,
                "result", Map.of(
                    "companyName", result.getCompanyName(),
                    "jobName", result.getJobName(),
                    "archetype", result.getArchetype(),
                    "scores", Map.of(
                        "A", result.getScoreA(),
                        "B", result.getScoreB(),
                        "C", result.getScoreC(),
                        "D", result.getScoreD(),
                        "E", result.getScoreE(),
                        "F", result.getScoreF(),
                        "G", result.getScoreG()
                    ),
                    "totalScore", result.getTotalScore(),
                    "recommendation", result.getTotalScore() >= EvaluationService.DEFAULT_THRESHOLD ? "投递" : "跳过",
                    "threshold", EvaluationService.DEFAULT_THRESHOLD
                )
            ));
        } catch (Exception e) {
            log.error("评估失败", e);
            return ResponseEntity.internalServerError().body(Map.of(
                "success", false, "message", "评估失败: " + e.getMessage()
            ));
        }
    }

    /**
     * 获取阈值配置
     */
    @GetMapping("/threshold")
    public ResponseEntity<Map<String, Object>> getThreshold() {
        return ResponseEntity.ok(Map.of(
            "threshold", EvaluationService.DEFAULT_THRESHOLD,
            "weights", Map.of(
                "A", 0.20, "B", 0.20, "C", 0.15,
                "D", 0.10, "E", 0.15, "F", 0.10, "G", 0.10
            )
        ));
    }

    /**
     * 获取原型列表
     */
    @GetMapping("/archetypes")
    public ResponseEntity<Map<String, Object>> getArchetypes() {
        return ResponseEntity.ok(Map.of(
            "success", true,
            "archetypes", new Object[]{
                Map.of("code", "Tech-Backend", "cnName", "技术后端", "description", "Java/Go/Python 后端"),
                Map.of("code", "Tech-Frontend", "cnName", "技术前端", "description", "React/Vue/Web 前端"),
                Map.of("code", "Tech-Data", "cnName", "技术数据", "description", "大数据/数据分析"),
                Map.of("code", "Tech-Ops", "cnName", "技术运维", "description", "DevOps/SRE/运维"),
                Map.of("code", "Product", "cnName", "产品经理", "description", "产品设计/需求"),
                Map.of("code", "Design", "cnName", "设计", "description", "UI/UX/视觉设计"),
                Map.of("code", "Operation", "cnName", "运营", "description", "用户/内容/活动运营"),
                Map.of("code", "General", "cnName", "通用/其他", "description", "其他类型")
            }
        ));
    }
}
