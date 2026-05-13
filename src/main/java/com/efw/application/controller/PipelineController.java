package com.efw.application.controller;

import com.efw.application.entity.PipelineEntry;
import com.efw.application.service.PipelineService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 管道管理控制器
 */
@Slf4j
@RestController
@RequestMapping("/api/pipeline")
@CrossOrigin(origins = "*")
@RequiredArgsConstructor
public class PipelineController {

    private final PipelineService pipelineService;

    /**
     * 获取所有管道条目
     */
    @GetMapping("/entries")
    public ResponseEntity<Map<String, Object>> getAllEntries() {
        List<PipelineEntry> entries = pipelineService.getAllEntries();
        return ResponseEntity.ok(Map.of("success", true, "entries", entries));
    }

    /**
     * 按状态筛选
     */
    @GetMapping("/entries/status/{status}")
    public ResponseEntity<Map<String, Object>> getByStatus(@PathVariable String status) {
        List<PipelineEntry> entries = pipelineService.getByStatus(status);
        return ResponseEntity.ok(Map.of("success", true, "entries", entries));
    }

    /**
     * 按平台筛选
     */
    @GetMapping("/entries/platform/{platform}")
    public ResponseEntity<Map<String, Object>> getByPlatform(@PathVariable String platform) {
        List<PipelineEntry> entries = pipelineService.getByPlatform(platform);
        return ResponseEntity.ok(Map.of("success", true, "entries", entries));
    }

    /**
     * 更新条目状态
     */
    @PutMapping("/entries/{id}/status")
    public ResponseEntity<Map<String, Object>> updateStatus(@PathVariable Long id, @RequestBody Map<String, String> body) {
        String status = body.get("status");
        if (status == null || status.isBlank()) {
            return ResponseEntity.badRequest().body(Map.of("success", false, "message", "status 不能为空"));
        }
        boolean updated = pipelineService.updateStatus(id, status);
        if (updated) {
            return ResponseEntity.ok(Map.of("success", true, "message", "状态已更新为: " + status));
        }
        return ResponseEntity.badRequest().body(Map.of("success", false, "message", "状态更新失败，请使用规范状态: " + PipelineService.CANONICAL_STATES));
    }

    /**
     * 创建管道条目
     */
    @PostMapping("/entries")
    public ResponseEntity<Map<String, Object>> createEntry(@RequestBody PipelineEntry entry) {
        try {
            PipelineEntry created = pipelineService.createEntry(
                entry.getPlatform(),
                entry.getCompanyName(),
                entry.getJobName(),
                entry.getScore(),
                entry.getStatus(),
                entry.getNotes()
            );
            return ResponseEntity.ok(Map.of("success", true, "entry", created));
        } catch (Exception e) {
            log.error("创建管道条目失败", e);
            return ResponseEntity.internalServerError().body(Map.of("success", false, "message", e.getMessage()));
        }
    }

    /**
     * 获取统计数据
     */
    @GetMapping("/stats")
    public ResponseEntity<Map<String, Object>> getStats() {
        PipelineService.PipelineStats stats = pipelineService.getStats();
        return ResponseEntity.ok(Map.of("success", true, "stats", stats));
    }

    /**
     * 获取规范状态列表
     */
    @GetMapping("/states")
    public ResponseEntity<Map<String, Object>> getStates() {
        return ResponseEntity.ok(Map.of(
            "success", true,
            "states", PipelineService.CANONICAL_STATES,
            "stateDescriptions", Map.of(
                "Evaluated", "已评估，待决定是否投递",
                "Applied", "已投递",
                "Responded", "HR 已回复",
                "Interview", "面试中",
                "Offer", "已拿到 Offer",
                "Rejected", "已拒绝",
                "Discarded", "已放弃/关闭",
                "SKIP", "跳过不投递"
            )
        ));
    }
}
