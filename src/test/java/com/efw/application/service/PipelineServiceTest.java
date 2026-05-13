package com.efw.application.service;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.*;

/**
 * PipelineService 状态规范化测试
 */
class PipelineServiceTest {

    @ParameterizedTest
    @CsvSource({
        "Evaluated, Evaluated",
        "evaluated, Evaluated",
        "已评估, Evaluated",
        "Applied, Applied",
        "已投递, Applied",
        "Interview, Interview",
        "面试中, Interview",
        "Offer, Offer",
        "已拿offer, Offer",
        "Rejected, Rejected",
        "已拒绝, Rejected",
        "SKIP, SKIP",
        "跳过, SKIP",
        "invalid_status, null",
    })
    @DisplayName("应正确规范化状态值")
    void shouldNormalizeStatuses(String input, String expected) {
        // PipelineService is instantiated with a null mapper since we're only testing normalizeStatus
        PipelineService service = new PipelineService(null);
        String result = service.normalizeStatus(input);
        if ("null".equals(expected)) {
            assertNull(result, "非法状态应返回 null");
        } else {
            assertEquals(expected, result);
        }
    }

    @Test
    @DisplayName("应包含所有 8 个规范状态")
    void shouldHaveEightCanonicalStates() {
        assertEquals(8, PipelineService.CANONICAL_STATES.size(),
            "管道应有 8 个规范状态");
    }
}
