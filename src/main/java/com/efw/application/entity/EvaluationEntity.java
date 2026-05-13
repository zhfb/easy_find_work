package com.efw.application.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("evaluation")
public class EvaluationEntity {
    @TableId(type = IdType.AUTO)
    private Long id;

    @TableField("encrypt_id")
    private String encryptId;

    @TableField("platform")
    private String platform;

    @TableField("company_name")
    private String companyName;

    @TableField("job_name")
    private String jobName;

    @TableField("archetype")
    private String archetype;

    @TableField("score_a")
    private Integer scoreA;

    @TableField("score_b")
    private Integer scoreB;

    @TableField("score_c")
    private Integer scoreC;

    @TableField("score_d")
    private Integer scoreD;

    @TableField("score_e")
    private Integer scoreE;

    @TableField("score_f")
    private Integer scoreF;

    @TableField("score_g")
    private Integer scoreG;

    @TableField("total_score")
    private Double totalScore;

    @TableField("evaluation_json")
    private String evaluationJson;

    @TableField("created_at")
    private LocalDateTime createdAt;
}
