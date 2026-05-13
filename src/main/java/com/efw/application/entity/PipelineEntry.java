package com.efw.application.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("pipeline")
public class PipelineEntry {
    @TableId(type = IdType.AUTO)
    private Long id;

    @TableField("entry_number")
    private Integer entryNumber;

    @TableField("entry_date")
    private String entryDate;

    @TableField("platform")
    private String platform;

    @TableField("company_name")
    private String companyName;

    @TableField("job_name")
    private String jobName;

    @TableField("score")
    private Double score;

    @TableField("status")
    private String status;

    @TableField("report_path")
    private String reportPath;

    @TableField("has_pdf")
    private Boolean hasPdf;

    @TableField("notes")
    private String notes;

    @TableField("created_at")
    private LocalDateTime createdAt;

    @TableField("updated_at")
    private LocalDateTime updatedAt;
}
