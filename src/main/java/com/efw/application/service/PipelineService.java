package com.efw.application.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.efw.application.entity.PipelineEntry;
import com.efw.application.mapper.PipelineMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

/**
 * 管道管理服务
 * 基于 Career-Ops / EFW 的 applications.md 范式适配到 SQLite
 * 规范状态: Evaluated, Applied, Responded, Interview, Offer, Rejected, Discarded, SKIP
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class PipelineService {

    private final PipelineMapper pipelineMapper;

    /** 规范状态 */
    public static final List<String> CANONICAL_STATES = Arrays.asList(
        "Evaluated", "Applied", "Responded", "Interview",
        "Offer", "Rejected", "Discarded", "SKIP"
    );

    /**
     * 创建管道条目
     */
    public PipelineEntry createEntry(String platform, String companyName, String jobName,
                                     Double score, String status, String notes) {
        PipelineEntry entry = new PipelineEntry();
        entry.setEntryNumber(getNextEntryNumber());
        entry.setEntryDate(LocalDate.now().toString());
        entry.setPlatform(platform);
        entry.setCompanyName(companyName);
        entry.setJobName(jobName);
        entry.setScore(score);
        entry.setStatus(normalizeStatus(status));
        entry.setHasPdf(false);
        entry.setNotes(notes);
        entry.setCreatedAt(LocalDateTime.now());
        entry.setUpdatedAt(LocalDateTime.now());
        pipelineMapper.insert(entry);
        log.info("管道条目已创建: #{} {}/{} 状态={} 评分={}",
            entry.getEntryNumber(), companyName, jobName, entry.getStatus(), score);
        return entry;
    }

    /**
     * 投递后自动创建管道条目
     */
    public PipelineEntry createFromDelivery(String platform, String companyName, String jobName,
                                            Double score, String encryptId) {
        PipelineEntry entry = createEntry(platform, companyName, jobName, score, "Applied", null);
        return entry;
    }

    /**
     * 更新条目状态
     */
    public boolean updateStatus(Long id, String newStatus) {
        String normalized = normalizeStatus(newStatus);
        if (normalized == null) {
            log.warn("非法状态值: {}", newStatus);
            return false;
        }
        PipelineEntry entry = pipelineMapper.selectById(id);
        if (entry == null) {
            log.warn("管道条目不存在: id={}", id);
            return false;
        }
        entry.setStatus(normalized);
        entry.setUpdatedAt(LocalDateTime.now());
        pipelineMapper.updateById(entry);
        return true;
    }

    /**
     * 获取所有管道条目
     */
    public List<PipelineEntry> getAllEntries() {
        return pipelineMapper.selectList(new LambdaQueryWrapper<PipelineEntry>()
            .orderByDesc(PipelineEntry::getEntryNumber));
    }

    /**
     * 按状态筛选
     */
    public List<PipelineEntry> getByStatus(String status) {
        return pipelineMapper.selectList(new LambdaQueryWrapper<PipelineEntry>()
            .eq(PipelineEntry::getStatus, normalizeStatus(status))
            .orderByDesc(PipelineEntry::getEntryNumber));
    }

    /**
     * 按平台筛选
     */
    public List<PipelineEntry> getByPlatform(String platform) {
        return pipelineMapper.selectList(new LambdaQueryWrapper<PipelineEntry>()
            .eq(PipelineEntry::getPlatform, platform)
            .orderByDesc(PipelineEntry::getEntryNumber));
    }

    /**
     * 获取统计数据
     */
    public PipelineStats getStats() {
        List<PipelineEntry> all = getAllEntries();
        PipelineStats stats = new PipelineStats();
        stats.setTotal(all.size());
        stats.setApplied((int) all.stream().filter(e -> "Applied".equals(e.getStatus())).count());
        stats.setInterview((int) all.stream().filter(e -> "Interview".equals(e.getStatus())).count());
        stats.setOffer((int) all.stream().filter(e -> "Offer".equals(e.getStatus())).count());
        stats.setRejected((int) all.stream().filter(e -> "Rejected".equals(e.getStatus())).count());
        stats.setEvaluated((int) all.stream().filter(e -> "Evaluated".equals(e.getStatus())).count());
        stats.setDiscarded((int) all.stream().filter(e -> "Discarded".equals(e.getStatus())).count());
        stats.setSkipped((int) all.stream().filter(e -> "SKIP".equals(e.getStatus())).count());
        stats.setResponded((int) all.stream().filter(e -> "Responded".equals(e.getStatus())).count());
        // 平均评分
        stats.setAvgScore(all.stream()
            .filter(e -> e.getScore() != null)
            .mapToDouble(PipelineEntry::getScore)
            .average().orElse(0));
        return stats;
    }

    /**
     * 获取下一个编号
     */
    private int getNextEntryNumber() {
        PipelineEntry last = pipelineMapper.selectOne(
            new LambdaQueryWrapper<PipelineEntry>()
                .orderByDesc(PipelineEntry::getEntryNumber)
                .last("LIMIT 1"));
        return (last != null && last.getEntryNumber() != null) ? last.getEntryNumber() + 1 : 1;
    }

    /**
     * 规范化状态值
     */
    public String normalizeStatus(String status) {
        if (status == null) return null;
        String s = status.trim().toLowerCase();

        // 别名映射到规范状态
        if (s.matches("evaluated|evaluada|已评估")) return "Evaluated";
        if (s.matches("applied|aplicado|enviada|sent|已投递|投递")) return "Applied";
        if (s.matches("responded|respondido|已回复")) return "Responded";
        if (s.matches("interview|entrevista|面试中|面试")) return "Interview";
        if (s.matches("offer|oferta|已拿offer|offer")) return "Offer";
        if (s.matches("rejected|rechazado|已拒绝|不合适")) return "Rejected";
        if (s.matches("discarded|descartado|已放弃|关闭")) return "Discarded";
        if (s.matches("skip|no_aplicar|跳过|不投递")) return "SKIP";

        // 如果已在规范列表中
        if (CANONICAL_STATES.contains(status)) return status;

        return null;
    }

    @lombok.Data
    public static class PipelineStats {
        private int total;
        private int evaluated;
        private int applied;
        private int responded;
        private int interview;
        private int offer;
        private int rejected;
        private int discarded;
        private int skipped;
        private double avgScore;
    }
}
