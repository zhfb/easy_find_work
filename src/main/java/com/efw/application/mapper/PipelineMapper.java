package com.efw.application.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.efw.application.entity.PipelineEntry;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface PipelineMapper extends BaseMapper<PipelineEntry> {
}
