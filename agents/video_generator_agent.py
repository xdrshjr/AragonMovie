"""Video generation agent"""
import asyncio
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path
from datetime import datetime

from agents.base_agent import BaseAgent
from services.video_service_factory import VideoServiceFactory
from services.veo3_service import Veo3Service, VideoGenerationError
from services.sora2_service import Sora2Service
from services.scene_continuity_judge_service import SceneContinuityJudgeService
from models.script_models import Scene, SubScene, CameraMovement
from utils.concurrency import ConcurrencyLimiter
from utils.prompt_optimizer import PromptOptimizer
from utils.video_utils import FFmpegProcessor
from utils.blocking import run_blocking
from config.settings import settings
import logging


class VideoGenerationAgent(BaseAgent):
    """视频生成Agent - 将分镜图片转换为视频片段"""

    def __init__(
        self,
        agent_id: str = "video_generator",
        config: Dict[str, Any] = None,
        output_dir: Optional[Path] = None
    ):
        super().__init__(agent_id, config or {})
        self.output_dir = output_dir or Path("./output/videos")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger(__name__)

        # 从config中获取服务类型（优先级：config > settings）
        service_type = self.config.get('video_service_type', None)  # None表示使用settings默认值

        # 获取服务配置覆盖（如果config中有自定义配置）
        service_config = self.config.get('video_service_config', {})

        # 使用工厂创建服务
        self.service = VideoServiceFactory.create_service(
            service_type=service_type,
            config_override=service_config
        )

        # 确定实际使用的服务类型
        actual_service_type = service_type or settings.video_service_type
        service_class_name = type(self.service).__name__

        # 并发限制 - 优先使用config中的配置，其次使用settings中的默认值
        # 视频生成较慢，建议降低并发数
        max_concurrent = self.config.get('max_concurrent', settings.video_max_concurrent)
        self.limiter = ConcurrencyLimiter(max_concurrent)

        # 日志记录
        self.logger.info(
            f"VideoGenerationAgent initialized with service: {actual_service_type} ({service_class_name}), "
            f"model: {self.service.model}, max_concurrent: {max_concurrent}"
        )
        self.logger.debug(f"Service base_url: {self.service.base_url}")

        # 提示词优化器
        self.prompt_optimizer = PromptOptimizer()

        # FFmpeg处理器（用于帧提取和视频拼接）
        self.ffmpeg_processor = FFmpegProcessor()

        # 项目路径（用于加载自定义场景图）
        self.project_path: Optional[Path] = None

        # 重试配置
        self.max_retries = self.config.get(
            'max_retries',
            settings.video_generation_max_retries
        )
        self.retry_delay = self.config.get(
            'retry_delay',
            settings.video_generation_retry_delay
        )
        self.retry_backoff = self.config.get(
            'retry_backoff',
            settings.video_generation_retry_backoff
        )

        # 场景连续性配置
        self.enable_scene_continuity = self.config.get(
            'enable_scene_continuity',
            getattr(settings, 'enable_scene_continuity', True)
        )
        self.continuity_frame_index = self.config.get(
            'continuity_frame_index',
            getattr(settings, 'continuity_frame_index', -5)
        )
        self.continuity_reference_weight = self.config.get(
            'continuity_reference_weight',
            getattr(settings, 'continuity_reference_weight', 0.5)
        )
        self.enable_smart_continuity_judge = self.config.get(
            'enable_smart_continuity_judge',
            getattr(settings, 'enable_smart_continuity_judge', True)
        )

        # 场景连续性判断服务
        self.continuity_judge = SceneContinuityJudgeService() if self.enable_smart_continuity_judge else None

        # 判断结果缓存
        self.continuity_judgments = {}

        if self.enable_scene_continuity:
            self.logger.info(
                f"Scene continuity enabled: frame_index={self.continuity_frame_index}, "
                f"reference_weight={self.continuity_reference_weight}, "
                f"smart_judge={self.enable_smart_continuity_judge}"
            )
    
    def set_project_path(self, project_path: Path):
        """
        设置项目路径，用于加载自定义场景图
        
        Args:
            project_path: 项目文件夹路径
        """
        self.project_path = project_path
        self.logger.info(f"Project path set to: {project_path}")

    async def execute(
        self,
        image_results: List[Dict[str, Any]],
        scenes: List[Scene],
        character_dict: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable] = None,
        scene_params: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        执行批量视频生成

        Args:
            image_results: 图片生成结果列表
            scenes: 对应的场景列表
            character_dict: 可选的角色字典，用于生成视频提示词
            progress_callback: 可选的进度回调函数
            scene_params: 可选的场景参数字典，格式为 {scene_id: {duration, prompt, camera_motion, motion_strength}}

        Returns:
            视频生成结果列表
        """
        if not await self.validate_input((image_results, scenes)):
            raise ValueError("Invalid input data")

        self.logger.info(f"Starting video generation for {len(image_results)} clips")

        # Store scene_params for use in generation
        self.scene_params = scene_params or {}

        try:
            results = []
            previous_video_path = None  # 跟踪前一个场景的视频路径
            previous_scene = None  # 跟踪前一个场景对象

            # 如果启用连续性，顺序处理；否则并发处理
            if self.enable_scene_continuity:
                self.logger.info("Processing scenes sequentially for continuity")
                for idx, (img_result, scene) in enumerate(zip(image_results, scenes)):
                    self.logger.info(f"Processing scene {idx + 1}/{len(scenes)}: {scene.scene_id}")

                    # 判断是否应该使用前一场景的参考帧
                    should_use_reference = False
                    if previous_video_path and previous_scene:
                        if self.enable_smart_continuity_judge and self.continuity_judge:
                            # 使用LLM智能判断
                            judgment = await self._judge_scene_continuity(
                                previous_scene,
                                scene,
                                character_dict
                            )
                            should_use_reference = judgment['should_use']
                            self.logger.info(
                                f"Scene continuity judgment for {scene.scene_id}: "
                                f"should_use={should_use_reference}, "
                                f"type={judgment['scene_type']}, "
                                f"confidence={judgment['confidence']:.2f}, "
                                f"reason={judgment['reason']}"
                            )
                        else:
                            # 不使用智能判断，默认都使用连续性
                            should_use_reference = True
                            self.logger.info(
                                f"Scene continuity for {scene.scene_id}: "
                                f"using reference (smart judge disabled)"
                            )

                    task_data = {
                        'image_result': img_result,
                        'scene': scene,
                        'character_dict': character_dict,
                        'previous_video_path': previous_video_path if should_use_reference else None
                    }

                    result = await self._generate_video_clip(task_data)
                    results.append(result)

                    # 更新前一个视频路径和场景（仅在成功时）
                    if result.get('success', False) and result.get('video_path'):
                        previous_video_path = result['video_path']
                        previous_scene = scene
                        self.logger.debug(f"Updated previous_video_path: {previous_video_path}")

                    # 调用进度回调
                    if progress_callback:
                        progress = (idx + 1) / len(scenes) * 100
                        progress_callback(progress)
            else:
                # 原有的并发处理逻辑
                self.logger.info("Processing scenes concurrently (continuity disabled)")
                tasks_data = []
                for img_result, scene in zip(image_results, scenes):
                    tasks_data.append({
                        'image_result': img_result,
                        'scene': scene,
                        'character_dict': character_dict,
                        'previous_video_path': None  # 并发模式下不使用前一视频
                    })

                # 并发执行
                results = await self.limiter.run_batch(
                    self._generate_video_clip,
                    tasks_data,
                    show_progress=True
                )

            # 统计成功和失败的场景
            success_count = sum(1 for r in results if r.get('success', False))
            failed_count = len(results) - success_count

            if failed_count > 0:
                failed_scenes = [r.get('scene_id', 'unknown') for r in results if not r.get('success', False)]
                self.logger.warning(
                    f"Video generation completed with failures: "
                    f"{success_count} succeeded, {failed_count} failed. "
                    f"Failed scenes: {', '.join(failed_scenes)}"
                )
            else:
                self.logger.info(f"All {success_count} video clips generated successfully")

            await self.on_complete(results)
            return results

        except Exception as e:
            await self.on_error(e)
            raise

    async def validate_input(self, input_data: tuple) -> bool:
        """验证输入数据"""
        image_results, scenes = input_data

        if not image_results or not scenes:
            return False

        if len(image_results) != len(scenes):
            self.logger.error("Image results and scenes count mismatch")
            return False

        return True

    async def _generate_video_clip(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成单个视频片段（带重试机制和智能提示词调整）
        支持带子场景的场景生成和场景连续性

        Args:
            task_data: 包含image_result、scene、character_dict和previous_video_path的字典

        Returns:
            视频生成结果
        """
        image_result = task_data['image_result']
        scene = task_data['scene']
        character_dict = task_data.get('character_dict')
        previous_video_path = task_data.get('previous_video_path')

        # 检查是否有子场景
        if scene.sub_scenes:
            self.logger.info(f"Scene {scene.scene_id} has {len(scene.sub_scenes)} sub-scenes, using hierarchical generation")
            return await self._generate_scene_with_subscenes(
                image_result,
                scene,
                character_dict,
                previous_video_path
            )
        else:
            # 普通场景，使用原有逻辑
            return await self._generate_simple_scene(
                image_result,
                scene,
                character_dict,
                previous_video_path
            )

    async def _generate_simple_scene(
        self,
        image_result: Dict[str, Any],
        scene: Scene,
        character_dict: Optional[Dict[str, Any]],
        previous_video_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成简单场景（无子场景）

        Args:
            image_result: 图片生成结果
            scene: 场景对象
            character_dict: 角色字典
            previous_video_path: 前一场景的视频路径（用于连续性）

        Returns:
            视频生成结果（包含success标志）
        """
        image_path = image_result['image_path']
        scene_id = scene.scene_id

        # 提取参考帧（如果启用连续性且存在前一视频）
        reference_frame_path = None
        if self.enable_scene_continuity and previous_video_path:
            try:
                reference_frame_path = await self._extract_reference_frame(
                    video_path=previous_video_path,
                    frame_index=self.continuity_frame_index
                )
                self.logger.info(f"Scene {scene_id}: Using reference frame from previous scene")
            except Exception as e:
                self.logger.warning(
                    f"Scene {scene_id}: Failed to extract reference frame: {e}. "
                    f"Continuing without reference frame."
                )
                reference_frame_path = None

        # 构建图片路径列表
        if reference_frame_path:
            image_paths = [image_path, reference_frame_path]
        else:
            image_paths = image_path  # 单张图片

        # 跟踪是否遇到音频过滤错误
        audio_filtered_error = False

        # 带重试的视频生成
        for attempt in range(self.max_retries + 1):
            try:
                result = await self._generate_video_clip_once(
                    image_paths,
                    scene,
                    scene_id,
                    character_dict,
                    attempt,
                    remove_dialogues=audio_filtered_error  # 如果之前遇到音频过滤错误，移除台词
                )
                # 标记成功
                result['success'] = True
                result['scene_id'] = scene_id
                self.logger.info(f"✓ Scene {scene_id} generated successfully")
                return result

            except VideoGenerationError as e:
                # 检查是否是音频过滤错误
                if e.error_type == 'audio_filtered':
                    audio_filtered_error = True
                    self.logger.warning(
                        f"Audio filtered error detected for scene {scene_id}. "
                        f"Will retry without dialogues in next attempt."
                    )

                # 检查是否可重试
                if not e.retryable:
                    self.logger.error(
                        f"✗ Scene {scene_id} failed: Non-retryable error: {e}"
                    )
                    # 返回错误结果而不是抛出异常
                    return {
                        'success': False,
                        'scene_id': scene_id,
                        'error': str(e),
                        'error_type': 'non_retryable',
                        'video_path': None
                    }

                # 检查是否还有重试次数
                if attempt < self.max_retries:
                    delay = self.retry_delay * (self.retry_backoff ** attempt)
                    retry_strategy = " (will remove dialogues)" if audio_filtered_error else ""
                    self.logger.warning(
                        f"Scene {scene_id} failed "
                        f"(attempt {attempt + 1}/{self.max_retries + 1}): {e}{retry_strategy}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(
                        f"✗ Scene {scene_id} failed after {self.max_retries + 1} attempts: {e}"
                    )
                    # 返回错误结果而不是抛出异常
                    return {
                        'success': False,
                        'scene_id': scene_id,
                        'error': str(e),
                        'error_type': 'max_retries_exceeded',
                        'video_path': None
                    }

            except Exception as e:
                # 其他异常（网络错误等）也进行重试
                if attempt < self.max_retries:
                    delay = self.retry_delay * (self.retry_backoff ** attempt)
                    self.logger.warning(
                        f"Scene {scene_id} failed with unexpected error "
                        f"(attempt {attempt + 1}/{self.max_retries + 1}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(
                        f"✗ Scene {scene_id} failed after {self.max_retries + 1} attempts: {e}"
                    )
                    # 返回错误结果而不是抛出异常
                    return {
                        'success': False,
                        'scene_id': scene_id,
                        'error': str(e),
                        'error_type': 'unexpected_error',
                        'video_path': None
                    }

    async def _generate_scene_with_subscenes(
        self,
        image_result: Dict[str, Any],
        scene: Scene,
        character_dict: Optional[Dict[str, Any]],
        previous_video_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成包含子场景的场景视频

        流程:
        1. 从图片生成基础场景视频
        2. 从基础视频提取指定帧
        3. 使用提取的帧生成所有子场景视频
        4. 拼接基础视频和所有子场景视频

        Args:
            image_result: 图片生成结果
            scene: 场景对象（包含子场景）
            character_dict: 角色字典
            previous_video_path: 前一场景的视频路径（用于连续性）

        Returns:
            最终拼接后的视频生成结果
        """
        scene_id = scene.scene_id
        self.logger.info(
            f"Generating hierarchical scene {scene_id} with {len(scene.sub_scenes)} sub-scenes"
        )

        try:
            # Step 1: 生成基础场景视频
            self.logger.info(f"Step 1/4: Generating base scene video for {scene_id}")
            base_video_result = await self._generate_simple_scene(
                image_result,
                scene,
                character_dict,
                previous_video_path  # 传递前一视频路径
            )

            # 检查基础场景是否生成成功
            if not base_video_result.get('success', False):
                self.logger.error(f"Base scene generation failed for {scene_id}")
                return {
                    'success': False,
                    'scene_id': scene_id,
                    'error': 'Base scene generation failed',
                    'error_type': 'base_scene_failed',
                    'video_path': None
                }

            base_video_path = base_video_result['video_path']
            self.logger.info(f"Base scene video generated: {base_video_path}")
            
            # Step 2: 从基础视频提取帧
            self.logger.info(
                f"Step 2/4: Extracting frame at index {scene.extract_frame_index} from base video"
            )
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            extracted_frame_path = self.output_dir / f"{scene_id}_extracted_frame_{timestamp}.png"
            
            try:
                # ffmpeg 子进程同步阻塞，必须放到线程池，避免卡住后端事件循环
                await run_blocking(
                    self.ffmpeg_processor.extract_frame,
                    video_path=base_video_path,
                    frame_index=scene.extract_frame_index,
                    output_path=str(extracted_frame_path)
                )
                self.logger.info(f"Frame extracted successfully: {extracted_frame_path}")
            except Exception as e:
                self.logger.error(f"Failed to extract frame from base video: {e}")
                return {
                    'success': False,
                    'scene_id': scene_id,
                    'error': f'Frame extraction failed: {str(e)}',
                    'error_type': 'frame_extraction_failed',
                    'video_path': None
                }
            
            # Step 3: 生成所有子场景视频
            self.logger.info(f"Step 3/4: Generating {len(scene.sub_scenes)} sub-scene videos")
            sub_scene_results = []
            failed_sub_scenes = []
            
            for idx, sub_scene in enumerate(scene.sub_scenes, 1):
                self.logger.info(
                    f"Generating sub-scene {idx}/{len(scene.sub_scenes)}: {sub_scene.sub_scene_id}"
                )
                
                try:
                    sub_video_result = await self._generate_subscene_video(
                        extracted_frame_path=str(extracted_frame_path),
                        sub_scene=sub_scene,
                        parent_scene=scene,
                        character_dict=character_dict
                    )
                    sub_scene_results.append(sub_video_result)
                    self.logger.info(
                        f"Sub-scene video generated: {sub_video_result['video_path']}"
                    )
                except Exception as e:
                    self.logger.error(
                        f"Failed to generate sub-scene {sub_scene.sub_scene_id}: {e}"
                    )
                    failed_sub_scenes.append(sub_scene.sub_scene_id)
                    # 继续生成其他子场景，不因为一个失败而中断
                    continue
            
            # 如果所有子场景都失败了，记录警告但仍使用基础视频
            if len(sub_scene_results) == 0 and len(scene.sub_scenes) > 0:
                self.logger.warning(
                    f"All {len(scene.sub_scenes)} sub-scenes failed for {scene_id}. "
                    f"Using base video only."
                )
            elif failed_sub_scenes:
                self.logger.warning(
                    f"{len(failed_sub_scenes)} sub-scenes failed for {scene_id}: "
                    f"{', '.join(failed_sub_scenes)}"
                )
            
            # Step 4: 拼接所有视频
            video_paths_to_concat = [base_video_path]
            video_paths_to_concat.extend([r['video_path'] for r in sub_scene_results])
            
            self.logger.info(
                f"Step 4/4: Concatenating base video with {len(sub_scene_results)} sub-scene videos"
            )
            
            # 生成最终拼接视频的路径
            final_video_path = self.output_dir / f"{scene_id}_final_{timestamp}.mp4"
            
            try:
                # 拼接同样是同步 ffmpeg 子进程调用
                await run_blocking(
                    self.ffmpeg_processor.concatenate_videos_filter,
                    video_paths=video_paths_to_concat,
                    output_path=str(final_video_path)
                )
                self.logger.info(f"Final scene video created: {final_video_path}")
            except Exception as e:
                self.logger.error(f"Failed to concatenate videos for {scene_id}: {e}")
                return {
                    'success': False,
                    'scene_id': scene_id,
                    'error': f'Video concatenation failed: {str(e)}',
                    'error_type': 'concatenation_failed',
                    'video_path': None
                }
            
            # 构建返回结果 - 标记为成功
            self.logger.info(f"✓ Hierarchical scene {scene_id} generated successfully")
            return {
                'success': True,
                'scene_id': scene_id,
                'video_path': str(final_video_path),
                'duration': scene.duration,
                'config': base_video_result['config'],
                'api_response': base_video_result['api_response'],
                'dialogues': [d.model_dump() for d in scene.dialogues],
                'has_subscenes': True,
                'base_video_path': base_video_path,
                'sub_scene_videos': [r['video_path'] for r in sub_scene_results],
                'failed_sub_scenes': failed_sub_scenes,
                'extracted_frame_path': str(extracted_frame_path)
            }
            
        except Exception as e:
            self.logger.error(f"✗ Hierarchical scene {scene_id} failed with unexpected error: {e}")
            return {
                'success': False,
                'scene_id': scene_id,
                'error': str(e),
                'error_type': 'unexpected_error',
                'video_path': None
            }

    async def _generate_subscene_video(
        self,
        extracted_frame_path: str,
        sub_scene: SubScene,
        parent_scene: Scene,
        character_dict: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        生成单个子场景视频
        
        Args:
            extracted_frame_path: 从基础视频提取的帧图片路径
            sub_scene: 子场景对象
            parent_scene: 父场景对象
            character_dict: 角色字典
            
        Returns:
            子场景视频生成结果
        """
        sub_scene_id = sub_scene.sub_scene_id
        self.logger.info(f"Generating sub-scene video: {sub_scene_id}")
        
        # 检查子场景是否有自定义基础图
        image_path_to_use = extracted_frame_path
        if sub_scene.base_image_filename:
            custom_image_path = await self._load_custom_subscene_image(sub_scene)
            if custom_image_path:
                image_path_to_use = custom_image_path
                self.logger.info(f"Using custom base image for sub-scene: {custom_image_path}")
            else:
                self.logger.warning(
                    f"Failed to load custom base image for sub-scene {sub_scene_id}, "
                    f"using extracted frame instead"
                )
        
        # 生成子场景视频提示词
        video_prompt = sub_scene.to_video_prompt(parent_scene, character_dict)
        self.logger.debug(f"Sub-scene original prompt: {video_prompt}")
        
        # 使用LLM优化子场景提示词
        optimized_prompt = await self.prompt_optimizer.optimize_video_prompt(video_prompt)
        self.logger.debug(f"Sub-scene optimized prompt: {optimized_prompt}")
        
        # 配置视频参数（继承或使用子场景的设置）
        camera_movement = sub_scene.camera_movement if sub_scene.camera_movement else parent_scene.camera_movement
        
        video_config = {
            'fps': self.config.get('fps', 30),
            'resolution': self.config.get('resolution', '1920x1080'),
            'motion_strength': self.config.get('motion_strength', 0.5),
            'camera_motion': self._map_camera_motion(camera_movement),
            'prompt': optimized_prompt
        }
        
        if sub_scene.duration is not None:
            video_config['duration'] = sub_scene.duration

        # 适配不同服务的参数（子场景也需要适配）
        if isinstance(self.service, Sora2Service):
            # Sora2特定参数适配
            self.logger.debug(f"Adapting sub-scene parameters for Sora2 service")

            # 1. 时长适配
            if 'duration' in video_config:
                original_duration = video_config['duration']
                allowed_durations = Sora2Service.SUPPORTED_DURATIONS
                sora_duration = min(allowed_durations, key=lambda x: abs(x - original_duration))

                if abs(sora_duration - original_duration) > 0.5:
                    self.logger.warning(
                        f"Sub-scene duration {original_duration}s adjusted to {sora_duration}s (Sora2 constraint)"
                    )
                video_config['duration'] = sora_duration

            # 2. 分辨率参数转换
            if 'resolution' in video_config:
                resolution = video_config.pop('resolution')
                if 'size' not in video_config:
                    video_config['size'] = resolution if 'x' in resolution.lower() else self.service.default_size

            # 3. 添加Sora2特有参数
            style = self.config.get('style') or getattr(self.service, 'default_style', None)
            if style:
                video_config['style'] = style

            video_config['watermark'] = getattr(self.service, 'watermark', False)
            video_config['private'] = getattr(self.service, 'private', False)

            # 4. 移除不支持的参数
            for param in ['motion_strength', 'camera_motion', 'fps']:
                if param in video_config:
                    video_config.pop(param)

        # 调用视频生成服务API生成子场景视频
        api_result = await self.service.image_to_video(
            image_path=image_path_to_use,
            **video_config
        )
        
        # 下载视频
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{sub_scene_id}_{timestamp}.mp4"
        save_path = self.output_dir / filename
        
        video_path = await self.service.download_video(
            api_result['video_url'],
            save_path
        )
        
        return {
            'sub_scene_id': sub_scene_id,
            'video_path': str(video_path),
            'duration': sub_scene.duration,
            'config': video_config,
            'api_response': api_result,
            'dialogues': [d.model_dump() for d in sub_scene.dialogues]
        }
    
    async def _load_custom_subscene_image(self, sub_scene: SubScene) -> Optional[str]:
        """
        加载子场景的自定义基础图
        
        Args:
            sub_scene: 子场景对象
            
        Returns:
            自定义图片路径，如果加载失败返回None
        """
        if not self.project_path:
            self.logger.error(
                f"Sub-scene {sub_scene.sub_scene_id} specifies custom base image "
                f"'{sub_scene.base_image_filename}', but project_path is not set."
            )
            return None
        
        # 构建自定义场景图路径
        scenes_folder = self.project_path / "scenes"
        custom_image_path = scenes_folder / sub_scene.base_image_filename
        
        if not custom_image_path.exists():
            self.logger.error(
                f"Custom base image not found for sub-scene {sub_scene.sub_scene_id}: "
                f"{custom_image_path}"
            )
            return None
        
        self.logger.info(
            f"Loading custom base image for sub-scene {sub_scene.sub_scene_id}: "
            f"{custom_image_path}"
        )
        
        # 复制图片到输出目录
        import shutil
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{sub_scene.sub_scene_id}_{timestamp}_custom.png"
        save_path = self.output_dir / filename
        
        try:
            shutil.copy2(custom_image_path, save_path)
            self.logger.info(f"Custom base image copied to: {save_path}")
            return str(save_path)
        except Exception as e:
            self.logger.error(f"Failed to copy custom base image: {e}")
            return None

    async def _extract_reference_frame(
        self,
        video_path: str,
        frame_index: int = -5
    ) -> str:
        """
        从视频中提取参考帧

        Args:
            video_path: 视频文件路径
            frame_index: 帧索引（负数表示倒数）

        Returns:
            提取的帧图片路径
        """
        output_dir = Path(self.output_dir) / "temp" / "reference_frames"
        output_dir.mkdir(parents=True, exist_ok=True)

        video_name = Path(video_path).stem
        frame_path = output_dir / f"{video_name}_frame_{abs(frame_index)}.png"

        # 使用 FFmpegProcessor 提取帧
        # ffmpeg 子进程是同步阻塞的：放到线程池执行，否则会卡住后端事件循环，
        # 导致 /api/v1/tasks/{id} 状态轮询超时（前端误判为生成失败）
        await run_blocking(
            self.ffmpeg_processor.extract_frame,
            video_path=video_path,
            frame_index=frame_index,
            output_path=str(frame_path)
        )

        self.logger.info(f"Extracted reference frame: {frame_path}")
        return str(frame_path)

    async def _judge_scene_continuity(
        self,
        previous_scene: Scene,
        current_scene: Scene,
        character_dict: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        判断当前场景是否应该使用前一场景的参考帧

        Args:
            previous_scene: 前一个场景
            current_scene: 当前场景
            character_dict: 角色字典

        Returns:
            判断结果字典
        """
        # 生成缓存键
        cache_key = f"{previous_scene.scene_id}_{current_scene.scene_id}"

        # 检查缓存
        if cache_key in self.continuity_judgments:
            self.logger.debug(f"Using cached continuity judgment for {cache_key}")
            return self.continuity_judgments[cache_key]

        # 调用判断服务
        judgment = await self.continuity_judge.should_use_continuity(
            previous_scene,
            current_scene,
            character_dict
        )

        # 缓存结果
        self.continuity_judgments[cache_key] = judgment

        return judgment

    async def _generate_video_clip_once(
        self,
        image_path,  # Union[str, List[str]]
        scene: Scene,
        scene_id: str,
        character_dict: Optional[Dict[str, Any]],
        attempt: int,
        remove_dialogues: bool = False
    ) -> Dict[str, Any]:
        """
        执行一次视频片段生成

        Args:
            image_path: 图片路径（单张或多张列表）
            scene: 场景对象
            scene_id: 场景ID
            character_dict: 角色字典
            attempt: 当前尝试次数（从0开始）
            remove_dialogues: 是否移除台词（用于音频过滤错误重试）

        Returns:
            视频生成结果
        """
        log_prefix = f"[Attempt {attempt + 1}] " if attempt > 0 else ""
        self.logger.info(f"{log_prefix}Generating video for scene: {scene_id}")

        # 如果需要移除台词，创建场景副本并清空对话
        if remove_dialogues and scene.dialogues:
            self.logger.info(f"Removing {len(scene.dialogues)} dialogue(s) from prompt due to audio filter")
            # 创建场景副本
            from copy import deepcopy
            scene = deepcopy(scene)
            scene.dialogues = []  # 清空对话列表

        # 生成视频提示词（包含对话信息）
        video_prompt = scene.to_video_prompt(character_dict)
        self.logger.debug(f"Original video prompt: {video_prompt}")

        # 使用LLM优化视频提示词
        optimized_video_prompt = await self.prompt_optimizer.optimize_video_prompt(video_prompt)
        self.logger.debug(f"Optimized video prompt: {optimized_video_prompt}")

        # 配置视频参数
        video_config = {
            'fps': self.config.get('fps', 30),
            'resolution': self.config.get('resolution', '1920x1080'),
            'motion_strength': self.config.get('motion_strength', 0.5),
            'camera_motion': self._map_camera_motion(scene.camera_movement),
            'prompt': optimized_video_prompt  # 使用优化后的提示词
        }

        # 添加参考权重（如果使用多图片）
        if isinstance(image_path, list) and len(image_path) > 1:
            video_config['reference_weight'] = self.continuity_reference_weight

        # Check if scene_params are provided (for quick mode)
        if hasattr(self, 'scene_params') and scene_id in self.scene_params:
            params = self.scene_params[scene_id]

            # Override with custom parameters if provided
            if params.get('duration') is not None:
                video_config['duration'] = params['duration']
            if params.get('prompt'):
                # Use custom prompt instead of generated one
                video_config['prompt'] = params['prompt']
            if params.get('camera_motion'):
                video_config['camera_motion'] = params['camera_motion']
            if params.get('motion_strength') is not None:
                video_config['motion_strength'] = params['motion_strength']

            self.logger.info(
                f"Using custom scene params for {scene_id}: "
                f"duration={params.get('duration')}, "
                f"camera_motion={params.get('camera_motion')}, "
                f"motion_strength={params.get('motion_strength')}"
            )
        # 只在scene指定了duration时才添加该参数，否则让视频模型自己决定时长
        elif scene.duration is not None:
            video_config['duration'] = scene.duration

        # 适配不同服务的参数
        if isinstance(self.service, Sora2Service):
            # Sora2特定参数适配
            self.logger.debug(f"Adapting parameters for Sora2 service")

            # 1. 时长适配：Sora2只支持4, 8, 12秒（基础模式）
            if 'duration' in video_config:
                original_duration = video_config['duration']
                allowed_durations = Sora2Service.SUPPORTED_DURATIONS
                # 找到最接近的支持时长
                sora_duration = min(allowed_durations, key=lambda x: abs(x - original_duration))

                if abs(sora_duration - original_duration) > 0.5:
                    self.logger.warning(
                        f"Duration {original_duration}s adjusted to {sora_duration}s (Sora2 constraint: {allowed_durations})"
                    )
                video_config['duration'] = sora_duration

            # 2. 分辨率参数：Sora2使用'size'而不是'resolution'
            if 'resolution' in video_config:
                # 将resolution转换为size
                resolution = video_config.pop('resolution')
                # 如果没有自定义size，使用分辨率或默认值
                if 'size' not in video_config:
                    # 尝试将resolution格式转换为size格式（如果格式相同）
                    video_config['size'] = resolution if 'x' in resolution.lower() else self.service.default_size
                    self.logger.debug(f"Converted resolution={resolution} to size={video_config['size']}")

            # 3. 添加Sora2特有参数
            # 如果config中指定了style，使用它
            style = self.config.get('style') or getattr(self.service, 'default_style', None)
            if style:
                video_config['style'] = style
                self.logger.debug(f"Using Sora2 style: {style}")

            # watermark和private参数
            video_config['watermark'] = getattr(self.service, 'watermark', False)
            video_config['private'] = getattr(self.service, 'private', False)

            # 4. 移除Sora2不支持的参数
            unsupported_params = ['motion_strength', 'camera_motion', 'fps']
            for param in unsupported_params:
                if param in video_config:
                    removed_value = video_config.pop(param)
                    self.logger.debug(f"Removed unsupported Sora2 parameter: {param}={removed_value}")

            # 日志记录最终参数
            self.logger.info(
                f"Sora2 video generation params: duration={video_config.get('duration')}s, "
                f"size={video_config.get('size')}, style={video_config.get('style', 'none')}"
            )
        else:
            # Veo3参数（保持现有逻辑）
            self.logger.debug(f"Using Veo3 service parameters (no adaptation needed)")

        # 调用视频生成服务API
        api_result = await self.service.image_to_video(
            image_path=image_path,
            **video_config
        )

        # 下载视频
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{scene_id}_{timestamp}.mp4"
        save_path = self.output_dir / filename

        video_path = await self.service.download_video(
            api_result['video_url'],
            save_path
        )

        return {
            'scene_id': scene_id,
            'video_path': str(video_path),
            'duration': scene.duration,
            'config': video_config,
            'api_response': api_result,
            'dialogues': [d.model_dump() for d in scene.dialogues]  # 新增：保留对话数据
        }

    def _map_camera_motion(self, movement: CameraMovement) -> str:
        """
        将Scene的camera_movement映射到Veo3的参数

        Args:
            movement: CameraMovement枚举

        Returns:
            Veo3 API支持的运动类型
        """
        motion_mapping = {
            CameraMovement.STATIC: 'static',
            CameraMovement.PAN: 'pan',
            CameraMovement.TILT: 'tilt',
            CameraMovement.ZOOM: 'zoom',
            CameraMovement.DOLLY: 'dolly',
            CameraMovement.TRACKING: 'tracking'
        }

        return motion_mapping.get(movement, 'static')

    async def close(self):
        """关闭资源"""
        service_name = type(self.service).__name__
        self.logger.info(f"Closing VideoGenerationAgent resources, service: {service_name}")

        await self.service.close()
        await self.prompt_optimizer.close()

        self.logger.info(f"VideoGenerationAgent resources closed successfully")
