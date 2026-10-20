"""
Drama Generation Orchestrator - 主控Agent协调器
"""

import asyncio
from typing import Dict, Any, Optional, Callable, List
from pathlib import Path
from agents.base_agent import BaseAgent
from agents.script_parser_agent import ScriptParserAgent
from agents.character_reference_agent import CharacterReferenceAgent
from agents.image_generator_agent import ImageGenerationAgent
from agents.video_generator_agent import VideoGenerationAgent
from agents.video_composer_agent import VideoComposerAgent
from models.script_models import Script
from config.settings import settings
import logging
import json
from datetime import datetime


class DramaGenerationOrchestrator(BaseAgent):
    """主控Agent - 协调整个短剧生成流程"""

    def __init__(
        self,
        agent_id: str = "orchestrator",
        config: Dict[str, Any] = None,
        output_dir: Optional[Path] = None,
        project_path: Optional[Path] = None
    ):
        super().__init__(agent_id, config or {})
        self.logger = logging.getLogger(__name__)

        # 设置输出目录（如果提供）
        self.output_dir = output_dir or Path("./output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 设置项目路径（用于加载自定义场景图）
        self.project_path = project_path

        # 设置项目特定日志
        self._setup_logging()

        # 构建各子目录路径
        char_ref_dir = self.output_dir / "character_references"
        images_dir = self.output_dir / "images"
        videos_dir = self.output_dir / "videos"
        final_dir = self.output_dir / "final"

        # 构建角色参考配置（合并settings和config）
        character_reference_config = {
            'character_reference_mode': settings.character_reference_mode,
            'reference_views': settings.reference_views,
            'reference_image_size': settings.reference_image_size,
            'reference_cfg_scale': settings.reference_cfg_scale,
            'reference_steps': settings.reference_steps,
            'character_art_style': settings.character_art_style,
            'max_reference_images': settings.max_reference_images,
        }
        # 允许config覆盖settings
        character_reference_config.update(self.config.get('character_reference', {}))

        # 初始化子Agent，传递输出目录
        self.script_parser = ScriptParserAgent()
        self.character_reference_agent = CharacterReferenceAgent(
            config=character_reference_config,
            output_dir=char_ref_dir
        )
        self.image_generator = ImageGenerationAgent(
            config=self.config.get('image', {}),
            output_dir=images_dir
        )
        self.video_generator = VideoGenerationAgent(
            config=self.config.get('video', {}),
            output_dir=videos_dir
        )
        self.video_composer = VideoComposerAgent(
            config=self.config.get('composer', {}),
            output_dir=final_dir
        )
        
        # 传递项目路径到agents（如果可用）
        if self.project_path:
            self.image_generator.set_project_path(self.project_path)
            self.video_generator.set_project_path(self.project_path)
            self.logger.info(f"Project path passed to agents: {self.project_path}")

        # 一致性控制开关
        self.enable_character_references = self.config.get(
            'enable_character_references',
            settings.enable_character_references
        )

        # 进度回调
        self.progress_callback: Optional[Callable] = None

        # 任务状态
        self.current_task_id: Optional[str] = None
        self.start_time: Optional[datetime] = None

    async def execute(
        self,
        script_text: str,
        output_filename: str = "drama.mp4",
        progress_callback: Optional[Callable] = None,
        character_images: Optional[Dict[str, Any]] = None,
        scene_images: Optional[Dict[str, str]] = None
    ) -> str:
        """
        执行完整的短剧生成流程

        Args:
            script_text: 剧本文本
            output_filename: 输出文件名
            progress_callback: 进度回调函数
            character_images: 角色图片配置字典（可选）
                格式: {character_name: {mode: "load"|"generate", images: [...], views: [...]}}
            scene_images: 场景图片映射字典（可选）
                格式: {scene_id: image_path} - 跳过这些场景的AI生成

        Returns:
            最终视频文件路径
        """
        self.progress_callback = progress_callback
        self.start_time = datetime.now()
        self.current_task_id = f"drama_{self.start_time.strftime('%Y%m%d_%H%M%S')}"

        # 启动全局进度条（如果启用）
        if self.config.get('enable_global_progress_bar', False):
            from utils.global_progress_display import get_global_progress_display
            progress_display = get_global_progress_display()
            progress_display.start()

        try:
            # 步骤1：解析剧本 (0% -> 5%)
            await self._update_progress(0, "Starting drama generation...")
            await self._update_progress(1, "Parsing script...")

            script = await self.script_parser.execute(script_text)

            await self._update_progress(
                5,
                f"Script parsed: {script.total_scenes} scenes, "
                f"{len(script.characters)} characters"
                + (f", {script.total_duration:.1f}s duration" if script.total_duration else "")
            )

            # 步骤2：生成或加载角色参考图 (5% -> 15%)
            reference_data = None
            if self.enable_character_references and script.characters:
                # Log character images configuration
                if character_images:
                    self.logger.info(
                        f"Orchestrator | Character images config received | "
                        f"characters={list(character_images.keys())} | "
                        f"count={len(character_images)}"
                    )
                    
                    # 检查是否有需要加载的图片
                    load_count = sum(
                        1 for cfg in character_images.values()
                        if cfg.get('mode') == 'load'
                    )
                    generate_count = len(character_images) - load_count
                    
                    if load_count > 0:
                        self.logger.info(
                            f"Orchestrator | Using custom character images | "
                            f"load={load_count} | generate={generate_count}"
                        )
                        await self._update_progress(
                            5, f"Processing character references ({load_count} custom, "
                            f"{generate_count} AI-generated)..."
                        )
                    else:
                        await self._update_progress(5, "Generating character reference sheets...")
                else:
                    self.logger.info("Orchestrator | No character images config, will use AI generation")
                    await self._update_progress(5, "Generating character reference sheets...")

                try:
                    reference_data = await self.character_reference_agent.execute(
                        script.characters,
                        character_images=character_images
                    )

                    # 统计成功生成/加载的参考图数量
                    success_count = sum(
                        1 for char_data in reference_data.values()
                        if 'error' not in char_data
                    )
                    
                    # Count by mode: generated_from_custom, generated (AI), or loaded_fallback
                    generated_from_custom_count = sum(
                        1 for char_data in reference_data.values()
                        if char_data.get('mode') == 'generated_from_custom'
                    )
                    generated_ai_count = sum(
                        1 for char_data in reference_data.values()
                        if char_data.get('mode') in ['single_multi_view', 'multiple_single_view']
                    )
                    loaded_fallback_count = sum(
                        1 for char_data in reference_data.values()
                        if char_data.get('mode') == 'loaded_fallback'
                    )

                    self.logger.info(
                        f"Orchestrator | Character references processed | "
                        f"total={len(script.characters)} | "
                        f"success={success_count} | "
                        f"generated_from_custom={generated_from_custom_count} | "
                        f"generated_ai={generated_ai_count} | "
                        f"loaded_fallback={loaded_fallback_count} | "
                        f"failed={len(script.characters) - success_count}"
                    )

                    await self._update_progress(
                        15,
                        f"Processed references for {success_count}/{len(script.characters)} characters "
                        f"({generated_from_custom_count} from custom, {generated_ai_count} AI-generated)"
                    )

                except Exception as e:
                    self.logger.warning(
                        f"Orchestrator | Character reference processing failed | "
                        f"error={type(e).__name__}: {str(e)}"
                    )
                    self.logger.warning("Continuing with prompt-only enhancement")
                    reference_data = None
                    await self._update_progress(15, "Skipped character references (using prompt enhancement)")
            else:
                self.logger.info("Orchestrator | Character references disabled, using prompt enhancement only")
                await self._update_progress(15, "Character references disabled, using prompt enhancement only")

            # 步骤3：生成分镜图片 (15% -> 45%)
            # 处理预生成的场景图片
            provided_scene_count = 0
            if scene_images:
                provided_scene_count = len(scene_images)
                self.logger.info(f"Using {provided_scene_count} pre-generated scene images")
                await self._update_progress(15, f"Processing {provided_scene_count} provided scene images...")
            else:
                await self._update_progress(15, "Generating storyboard images with character consistency...")

            image_results = await self.image_generator.execute_concurrent(
                script.scenes,
                script=script,
                reference_data=reference_data,
                progress_callback=self._create_sub_progress_callback(15, 45),
                scene_images=scene_images
            )
            
            # 统计使用自定义基础图的场景数量
            custom_image_count = sum(1 for result in image_results if result.get('from_custom_base', False))
            provided_count = sum(1 for result in image_results if result.get('from_provided', False))
            ai_generated_count = len(image_results) - custom_image_count - provided_count
            
            stats_parts = []
            if ai_generated_count > 0:
                stats_parts.append(f"{ai_generated_count} AI-generated")
            if custom_image_count > 0:
                stats_parts.append(f"{custom_image_count} custom")
            if provided_count > 0:
                stats_parts.append(f"{provided_count} provided")
            
            stats_message = ", ".join(stats_parts) if stats_parts else "no images"
            self.logger.info(f"Image generation complete: {stats_message}")

            await self._update_progress(
                45,
                f"Processed {len(image_results)} scene images ({stats_message})"
            )

            # 步骤4：生成视频片段 (45% -> 75%)
            await self._update_progress(45, "Converting images to videos...")

            # 构建角色字典，用于生成视频提示词
            character_dict = {char.name: char for char in script.characters}

            video_results = await self.video_generator.execute(
                image_results,
                script.scenes,
                character_dict=character_dict
            )
            
            # 检查是否有失败的场景
            failed_scenes = [r for r in video_results if not r.get('success', False)]
            success_scenes = [r for r in video_results if r.get('success', False)]

            if failed_scenes:
                # 收集详细的失败信息
                failed_details = []
                for failed in failed_scenes:
                    scene_id = failed.get('scene_id', 'unknown')
                    error_type = failed.get('error_type', 'unknown')
                    error_msg = failed.get('error', 'Unknown error')
                    failed_details.append({
                        'scene_id': scene_id,
                        'error_type': error_type,
                        'error': error_msg
                    })

                # 生成详细的错误报告
                failed_ids = ', '.join([f.get('scene_id', 'unknown') for f in failed_scenes])
                error_summary = f"Video generation completed with errors: {len(success_scenes)} succeeded, {len(failed_scenes)} failed (scenes: {failed_ids})"

                # 添加详细错误信息到日志
                self.logger.warning(error_summary)
                for detail in failed_details:
                    self.logger.error(
                        f"  - Scene {detail['scene_id']}: {detail['error_type']} - {detail['error']}"
                    )

                await self._update_progress(
                    75,
                    error_summary
                )

                # 如果所有场景都失败了，抛出详细的异常
                if len(success_scenes) == 0:
                    error_types = {}
                    for detail in failed_details:
                        error_type = detail['error_type']
                        error_types[error_type] = error_types.get(error_type, 0) + 1

                    error_type_summary = ', '.join([f"{count} {etype}" for etype, count in error_types.items()])

                    detailed_message = (
                        f"All video scenes failed to generate. "
                        f"Error types: {error_type_summary}. "
                        f"\nFailed scenes:\n" +
                        '\n'.join([f"  - {d['scene_id']}: {d['error']}" for d in failed_details[:5]])  # Show first 5
                    )

                    if len(failed_details) > 5:
                        detailed_message += f"\n  ... and {len(failed_details) - 5} more"

                    raise Exception(detailed_message)

                # 检查成功率是否达到最小要求（如果配置了）
                min_success_rate = self.config.get('min_success_rate', 0.0)  # Default: allow any success rate
                success_rate = len(success_scenes) / len(video_results)

                if success_rate < min_success_rate:
                    error_types = {}
                    for detail in failed_details:
                        error_type = detail['error_type']
                        error_types[error_type] = error_types.get(error_type, 0) + 1

                    error_type_summary = ', '.join([f"{count} {etype}" for etype, count in error_types.items()])

                    detailed_message = (
                        f"Video generation success rate ({success_rate:.1%}) is below minimum required ({min_success_rate:.1%}). "
                        f"Error types: {error_type_summary}. "
                        f"\nFailed scenes:\n" +
                        '\n'.join([f"  - {d['scene_id']}: {d['error']}" for d in failed_details[:5]])
                    )

                    if len(failed_details) > 5:
                        detailed_message += f"\n  ... and {len(failed_details) - 5} more"

                    raise Exception(detailed_message)

                # 继续处理成功的场景，但记录警告
                self.logger.warning(
                    f"Continuing with {len(success_scenes)} successful scenes "
                    f"(success rate: {success_rate:.1%})"
                )
            else:
                await self._update_progress(
                    75,
                    f"Generated {len(video_results)} video clips successfully"
                )

            # 步骤5：合成最终视频 (75% -> 95%)
            await self._update_progress(75, "Composing final video...")

            final_video_path = await self.video_composer.execute(
                video_results,
                output_filename=output_filename,
                bgm_path=self.config.get('bgm_path'),
                add_subtitles=self.config.get('add_subtitles', False),
                # 合成实际在专用线程池中执行（不阻塞事件循环），进度 75% -> 95%
                progress_callback=self._create_sub_progress_callback(75, 95)
            )

            await self._update_progress(95, "Saving metadata...")

            # 步骤6：保存元数据 (95% -> 100%)
            await self._save_metadata(script, final_video_path, reference_data)

            await self._update_progress(100, "Drama generation completed!")

            # 计算总耗时
            elapsed_time = (datetime.now() - self.start_time).total_seconds()
            self.logger.info(f"Total generation time: {elapsed_time:.2f}s")

            # 完成全局进度条（如果启用）
            if self.config.get('enable_global_progress_bar', False):
                from utils.global_progress_display import get_global_progress_display
                progress_display = get_global_progress_display()
                progress_display.finish()

            await self.on_complete(final_video_path)
            return final_video_path

        except Exception as e:
            self.logger.error(f"Drama generation failed: {e}")

            # 完成全局进度条（如果启用）
            if self.config.get('enable_global_progress_bar', False):
                from utils.global_progress_display import get_global_progress_display
                progress_display = get_global_progress_display()
                progress_display.finish()

            await self.on_error(e)
            raise

    async def execute_quick_mode(
        self,
        scenes_config: List[Any],
        scene_image_paths: Dict[str, str],
        scene_params: Dict[str, Dict[str, Any]],
        output_filename: str = "quick_mode.mp4",
        progress_callback: Optional[Callable] = None
    ) -> str:
        """
        Execute quick mode workflow - bypass script parsing and image generation

        Args:
            scenes_config: List of Scene objects (minimal)
            scene_image_paths: Dict mapping scene_id to image file path
            scene_params: Dict mapping scene_id to parameters (duration, prompt, camera_motion, motion_strength)
            output_filename: Output video filename
            progress_callback: Progress callback function

        Returns:
            Final video file path
        """
        self.progress_callback = progress_callback
        self.start_time = datetime.now()
        self.current_task_id = f"quick_{self.start_time.strftime('%Y%m%d_%H%M%S')}"

        self.logger.info(
            f"Orchestrator | Starting quick mode | "
            f"task_id={self.current_task_id} | "
            f"scene_count={len(scenes_config)}"
        )

        # Start global progress bar if enabled
        if self.config.get('enable_global_progress_bar', False):
            from utils.global_progress_display import get_global_progress_display
            progress_display = get_global_progress_display()
            progress_display.start()

        try:
            # Step 1: Prepare image results (0% -> 10%)
            await self._update_progress(0, "Starting quick mode generation...")
            await self._update_progress(5, "Preparing scene images...")

            image_results = []
            for scene in scenes_config:
                scene_id = scene.scene_id
                image_path = scene_image_paths.get(scene_id)

                if not image_path:
                    raise ValueError(f"Missing image path for scene: {scene_id}")

                image_results.append({
                    'scene_id': scene_id,
                    'image_path': image_path,
                    'success': True,
                    'from_quick_mode': True
                })

            await self._update_progress(
                10,
                f"Prepared {len(image_results)} scene images"
            )

            # Step 2: Generate videos (10% -> 70%)
            await self._update_progress(10, "Generating videos from images...")

            video_results = await self.video_generator.execute(
                image_results,
                scenes_config,
                character_dict={},  # No characters in quick mode
                progress_callback=self._create_sub_progress_callback(10, 70),
                scene_params=scene_params  # Pass scene parameters
            )

            # Check for failures
            failed_scenes = [r for r in video_results if not r.get('success', False)]
            success_scenes = [r for r in video_results if r.get('success', False)]

            if failed_scenes:
                failed_ids = ', '.join([r.get('scene_id', 'unknown') for r in failed_scenes])
                error_message = f"Video generation completed with errors: {len(success_scenes)} succeeded, {len(failed_scenes)} failed (scenes: {failed_ids})"
                self.logger.warning(error_message)
                await self._update_progress(70, error_message)

                if len(success_scenes) == 0:
                    raise Exception("All video scenes failed to generate")
            else:
                await self._update_progress(
                    70,
                    f"Generated {len(video_results)} video clips successfully"
                )

            # Step 3: Compose final video (70% -> 95%)
            await self._update_progress(70, "Composing final video...")

            final_video_path = await self.video_composer.execute(
                video_results,
                output_filename=output_filename,
                bgm_path=self.config.get('bgm_path'),
                add_subtitles=False,  # No subtitles in quick mode
                # 合成实际在专用线程池中执行（不阻塞事件循环），进度 70% -> 95%
                progress_callback=self._create_sub_progress_callback(70, 95)
            )

            await self._update_progress(95, "Saving metadata...")

            # Step 4: Save metadata (95% -> 100%)
            await self._save_quick_mode_metadata(
                scenes_config,
                scene_params,
                final_video_path
            )

            await self._update_progress(100, "Quick mode generation completed!")

            # Calculate elapsed time
            elapsed_time = (datetime.now() - self.start_time).total_seconds()
            self.logger.info(
                f"Orchestrator | Quick mode completed | "
                f"task_id={self.current_task_id} | "
                f"duration={elapsed_time:.2f}s"
            )

            # Finish global progress bar if enabled
            if self.config.get('enable_global_progress_bar', False):
                from utils.global_progress_display import get_global_progress_display
                progress_display = get_global_progress_display()
                progress_display.finish()

            await self.on_complete(final_video_path)
            return final_video_path

        except Exception as e:
            self.logger.error(f"Quick mode generation failed: {e}")

            # Finish global progress bar if enabled
            if self.config.get('enable_global_progress_bar', False):
                from utils.global_progress_display import get_global_progress_display
                progress_display = get_global_progress_display()
                progress_display.finish()

            await self.on_error(e)
            raise

    async def _save_quick_mode_metadata(
        self,
        scenes: List[Any],
        scene_params: Dict[str, Dict[str, Any]],
        video_path: str
    ):
        """
        Save quick mode generation metadata

        Args:
            scenes: List of Scene objects
            scene_params: Scene parameters dict
            video_path: Video file path
        """
        try:
            metadata = {
                'task_id': self.current_task_id,
                'mode': 'quick',
                'generated_at': datetime.now().isoformat(),
                'scene_info': {
                    'total_scenes': len(scenes),
                    'scene_params': scene_params
                },
                'output': {
                    'video_path': video_path,
                    'filename': Path(video_path).name
                },
                'config': self.config,
                'generation_time': (datetime.now() - self.start_time).total_seconds()
            }

            # Save metadata
            metadata_path = Path(video_path).with_suffix('.json')

            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            self.logger.info(f"Quick mode metadata saved: {metadata_path}")

        except Exception as e:
            self.logger.error(f"Failed to save quick mode metadata: {e}")

    async def validate_input(self, script_text: str) -> bool:
        """验证输入剧本"""
        if not script_text or not isinstance(script_text, str):
            return False

        if len(script_text.strip()) < 10:
            self.logger.error("Script text too short")
            return False

        return True

    def _setup_logging(self):
        """
        设置项目特定日志配置

        根据config中的log_file和log_level配置日志处理器
        """
        log_file = self.config.get('log_file')
        log_level = self.config.get('log_level', 'INFO')

        if not log_file:
            # 如果未指定日志文件，使用默认路径
            log_file = self.output_dir / "generation.log"
        else:
            log_file = Path(log_file)

        # 确保日志文件的父目录存在
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # 配置根日志记录器
        root_logger = logging.getLogger()

        # 设置日志级别
        numeric_level = getattr(logging, log_level.upper(), logging.INFO)
        root_logger.setLevel(numeric_level)

        # 检查是否已经存在文件处理器（避免重复添加）
        has_file_handler = any(
            isinstance(h, logging.FileHandler) and h.baseFilename == str(log_file.absolute())
            for h in root_logger.handlers
        )

        if not has_file_handler:
            # 创建文件处理器
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(numeric_level)

            # 设置格式
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(formatter)

            # 添加到根记录器
            root_logger.addHandler(file_handler)

            self.logger.info(f"Logging configured: level={log_level}, file={log_file}")

        # 如果启用了全局进度条，配置日志系统
        if self.config.get('enable_global_progress_bar', False):
            from utils.global_progress_display import configure_logging_with_progress_bar
            configure_logging_with_progress_bar(
                log_level=numeric_level,
                log_file=str(log_file)
            )

    async def _update_progress(self, percent: float, message: str):
        """
        更新进度

        Args:
            percent: 进度百分比（0-100）
            message: 进度消息
        """
        self.logger.info(f"Progress: {percent}% - {message}")

        # 更新全局进度条（如果启用）
        if self.config.get('enable_global_progress_bar', False):
            from utils.global_progress_display import get_global_progress_display
            progress_display = get_global_progress_display()
            progress_display.update(percent, message)

        if self.progress_callback:
            if asyncio.iscoroutinefunction(self.progress_callback):
                await self.progress_callback(percent, message)
            else:
                self.progress_callback(percent, message)

    def _create_sub_progress_callback(
        self,
        start_percent: float,
        end_percent: float
    ) -> Callable:
        """
        创建子任务的进度回调

        Args:
            start_percent: 起始百分比
            end_percent: 结束百分比

        Returns:
            进度回调函数
        """
        async def sub_progress_callback(sub_percent: float, message: str):
            # 将子任务进度映射到总进度
            total_percent = start_percent + (end_percent - start_percent) * (sub_percent / 100)
            await self._update_progress(total_percent, message)

        return sub_progress_callback

    async def _save_metadata(self, script: Script, video_path: str, reference_data: Optional[Dict] = None):
        """
        保存生成元数据

        Args:
            script: 剧本对象
            video_path: 视频文件路径
            reference_data: 角色参考数据（可选）
        """
        try:
            metadata = {
                'task_id': self.current_task_id,
                'generated_at': datetime.now().isoformat(),
                'script_info': {
                    'title': script.title,
                    'total_scenes': script.total_scenes,
                    'total_duration': script.total_duration,
                    'character_count': len(script.characters)
                },
                'output': {
                    'video_path': video_path,
                    'filename': Path(video_path).name
                },
                'consistency': {
                    'character_references_enabled': self.enable_character_references,
                    'references_generated': reference_data is not None,
                    'character_reference_count': len(reference_data) if reference_data else 0
                },
                'config': self.config,
                'generation_time': (datetime.now() - self.start_time).total_seconds()
            }

            # 保存元数据
            metadata_path = Path(video_path).with_suffix('.json')

            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            self.logger.info(f"Metadata saved: {metadata_path}")

        except Exception as e:
            self.logger.error(f"Failed to save metadata: {e}")
            # 不抛出异常，因为元数据保存失败不应影响主流程

    async def get_task_status(self) -> Dict[str, Any]:
        """
        获取当前任务状态

        Returns:
            任务状态信息
        """
        if not self.current_task_id:
            return {
                'status': 'idle',
                'message': 'No task running'
            }

        elapsed_time = (datetime.now() - self.start_time).total_seconds()

        return {
            'task_id': self.current_task_id,
            'status': self.state.value,
            'elapsed_time': elapsed_time,
            'start_time': self.start_time.isoformat()
        }

    async def cancel_task(self):
        """取消当前任务"""
        if self.current_task_id:
            self.logger.warning(f"Canceling task: {self.current_task_id}")
            self.current_task_id = None
            # 这里可以添加更多的清理逻辑

    async def close(self):
        """关闭所有子Agent资源"""
        try:
            await self.character_reference_agent.close()
            await self.image_generator.close()
            await self.video_generator.close()
            await self.video_composer.close()
            self.logger.info("Orchestrator closed successfully")
        except Exception as e:
            self.logger.error(f"Error closing orchestrator: {e}")


class SimpleDramaGenerator:
    """简化的短剧生成接口（用于快速使用）"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化生成器

        Args:
            config: 配置字典
        """
        self.orchestrator = DramaGenerationOrchestrator(config=config or {})
        self.logger = logging.getLogger(__name__)

    async def generate_from_file(
        self,
        script_file: str,
        output_file: str = "output.mp4",
        progress_callback: Optional[Callable] = None
    ) -> str:
        """
        从剧本文件生成视频

        Args:
            script_file: 剧本文件路径
            output_file: 输出视频文件名
            progress_callback: 进度回调

        Returns:
            生成的视频文件路径
        """
        # 读取剧本文件
        with open(script_file, 'r', encoding='utf-8') as f:
            script_text = f.read()

        # 生成视频
        return await self.generate(script_text, output_file, progress_callback)

    async def generate(
        self,
        script_text: str,
        output_file: str = "output.mp4",
        progress_callback: Optional[Callable] = None
    ) -> str:
        """
        从剧本文本生成视频

        Args:
            script_text: 剧本文本
            output_file: 输出视频文件名
            progress_callback: 进度回调

        Returns:
            生成的视频文件路径
        """
        try:
            return await self.orchestrator.execute(
                script_text,
                output_filename=output_file,
                progress_callback=progress_callback
            )
        except Exception as e:
            self.logger.error(f"Generation failed: {e}")
            raise

    async def close(self):
        """关闭生成器"""
        await self.orchestrator.close()
