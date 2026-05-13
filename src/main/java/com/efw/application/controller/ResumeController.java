package com.efw.application.controller;

import com.efw.application.service.ResumeService;
import com.efw.application.service.ResumeService.ResumeAnalysisResult;
import com.efw.application.service.ResumeService.ResumeRequest;
import com.efw.application.service.ResumeService.ResumeResult;
import com.efw.application.service.ResumeService.ResumeUploadResult;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.Map;

/**
 * 简历管理控制器
 */
@Slf4j
@RestController
@RequestMapping("/api/resume")
@CrossOrigin(origins = "*")
@RequiredArgsConstructor
public class ResumeController {

    private final ResumeService resumeService;

    /**
     * 生成简历
     */
    @PostMapping("/generate")
    public ResponseEntity<Map<String, Object>> generate(@RequestBody ResumeRequest request) {
        try {
            ResumeResult result = resumeService.generateResume(request);
            return ResponseEntity.ok(Map.of(
                "success", result.isSuccess(),
                "source", result.getSource(),
                "path", result.getPath() != null ? result.getPath() : "",
                "error", result.getError() != null ? result.getError() : "",
                "message", result.isSuccess() ? "简历已生成" : "简历生成失败"
            ));
        } catch (Exception e) {
            log.error("简历生成失败", e);
            return ResponseEntity.internalServerError().body(Map.of(
                "success", false, "message", "简历生成失败: " + e.getMessage()
            ));
        }
    }

    /**
     * 上传简历文件 (PDF/DOCX) 并解析
     */
    @PostMapping("/upload")
    public ResponseEntity<Map<String, Object>> upload(@RequestParam("file") MultipartFile file) {
        try {
            ResumeUploadResult uploadResult = resumeService.uploadResume(file);
            if (!uploadResult.isSuccess()) {
                return ResponseEntity.badRequest().body(Map.of(
                    "success", false, "message", uploadResult.getError()
                ));
            }
            return ResponseEntity.ok(Map.of(
                "success", true,
                "fileName", uploadResult.getFileName(),
                "filePath", uploadResult.getFilePath(),
                "extractedText", uploadResult.getExtractedText(),
                "message", "文件上传成功，文本已提取"
            ));
        } catch (Exception e) {
            log.error("简历上传失败", e);
            return ResponseEntity.internalServerError().body(Map.of(
                "success", false, "message", "上传失败: " + e.getMessage()
            ));
        }
    }

    /**
     * AI 分析简历文本
     */
    @PostMapping("/analyze")
    public ResponseEntity<Map<String, Object>> analyze(@RequestBody Map<String, String> body) {
        try {
            String text = body.get("text");
            if (text == null || text.isBlank()) {
                return ResponseEntity.badRequest().body(Map.of(
                    "success", false, "message", "文本内容不能为空"
                ));
            }
            ResumeAnalysisResult result = resumeService.analyzeResume(text);
            return ResponseEntity.ok(Map.of(
                "success", result.isSuccess(),
                "skills", result.getSkills(),
                "experience", result.getExperience(),
                "education", result.getEducation(),
                "yearsOfExperience", result.getYearsOfExperience(),
                "targetRoles", result.getTargetRoles(),
                "message", result.isSuccess() ? "分析完成" : result.getError()
            ));
        } catch (Exception e) {
            log.error("简历分析失败", e);
            return ResponseEntity.internalServerError().body(Map.of(
                "success", false, "message", "分析失败: " + e.getMessage()
            ));
        }
    }

    /**
     * 获取简历列表
     */
    @GetMapping("/list")
    public ResponseEntity<Map<String, Object>> list() {
        return ResponseEntity.ok(Map.of(
            "success", true,
            "resumes", resumeService.getResumeList(),
            "reviews", resumeService.getReviewList()
        ));
    }
}
