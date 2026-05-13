package com.efw.application.init;

import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.CommandLineRunner;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/**
 * 自动创建 evaluation 和 pipeline 表（SQLite 不支持 CREATE TABLE IF NOT EXISTS 的完整语法）
 */
@Slf4j
@Component
public class PipelineTableInitializer implements CommandLineRunner {

    private final JdbcTemplate jdbcTemplate;

    public PipelineTableInitializer(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void run(String... args) {
        createEvaluationTable();
        createPipelineTable();
        alterBossConfigTable();
    }

    /**
     * 向 boss_config 表添加 min_score_threshold 列（如果不存在）
     */
    private void alterBossConfigTable() {
        try {
            jdbcTemplate.execute("ALTER TABLE boss_config ADD COLUMN min_score_threshold REAL DEFAULT 3.5");
            log.info("boss_config 表已添加 min_score_threshold 列");
        } catch (Exception e) {
            // SQLite 不支持 IF NOT EXISTS for ALTER TABLE，列已存在时会出错，忽略即可
            log.debug("min_score_threshold 列已存在，跳过");
        }
    }

    private void createEvaluationTable() {
        String sql = "CREATE TABLE IF NOT EXISTS evaluation (" +
            "id INTEGER PRIMARY KEY AUTOINCREMENT," +
            "encrypt_id TEXT," +
            "platform TEXT DEFAULT 'boss'," +
            "company_name TEXT," +
            "job_name TEXT," +
            "archetype TEXT," +
            "score_a INTEGER DEFAULT 3," +
            "score_b INTEGER DEFAULT 3," +
            "score_c INTEGER DEFAULT 3," +
            "score_d INTEGER DEFAULT 3," +
            "score_e INTEGER DEFAULT 3," +
            "score_f INTEGER DEFAULT 3," +
            "score_g INTEGER DEFAULT 3," +
            "total_score REAL," +
            "evaluation_json TEXT," +
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP" +
            ")";
        try {
            jdbcTemplate.execute(sql);
            log.info("evaluation 表已就绪");
        } catch (Exception e) {
            log.error("创建 evaluation 表失败", e);
        }
    }

    private void createPipelineTable() {
        String sql = "CREATE TABLE IF NOT EXISTS pipeline (" +
            "id INTEGER PRIMARY KEY AUTOINCREMENT," +
            "entry_number INTEGER UNIQUE," +
            "entry_date TEXT," +
            "platform TEXT," +
            "company_name TEXT," +
            "job_name TEXT," +
            "score REAL," +
            "status TEXT DEFAULT 'Evaluated'," +
            "report_path TEXT," +
            "has_pdf INTEGER DEFAULT 0," +
            "notes TEXT," +
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP," +
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP" +
            ")";
        try {
            jdbcTemplate.execute(sql);
            log.info("pipeline 表已就绪");
        } catch (Exception e) {
            log.error("创建 pipeline 表失败", e);
        }
    }
}
