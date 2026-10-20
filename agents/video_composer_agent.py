"""
Video Composer Agent - 视频合成Agent

合成过程（moviepy / ffmpeg）是完全同步且耗时的。它必须运行在**事件循环之外**
（见 ``utils/blocking.run_media_blocking``），否则 uvicorn 单 worker 的
``GET /api/v1/tasks/{id}`` 会在合成的几分钟里全部排队等待，前端只能看到超时。
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agents.base_agent import BaseAgent
from moviepy import (
    VideoFileClip,
    concatenate_videoclips,
    CompositeVideoClip,
    AudioFileClip,
    TextClip
)
from moviepy.audio.AudioClip import CompositeAudioClip
from moviepy.audio.fx import AudioLoop
from moviepy.video.fx import FadeIn, FadeOut
from utils.blocking import run_media_blocking
from utils.video_utils import FFmpegProcessor

ProgressCallback = Callable[[float, str], Any]

# proglog 在 moviepy 2.x 里用 ``iter_frames`` 的 bar 名 "frame_index" 汇报写片进度，
# 旧版本/其它调用路径可能用 "t"。两者都接受，其余 bar 忽略。
_PROGRESS_BARS = ("frame_index", "t")


class VideoComposerAgent(BaseAgent):
    """视频合成Agent - 将所有片段合成为完整短剧"""

    def __init__(
        self,
        agent_id: str = "video_composer",
        config: Dict[str, Any] = None,
        output_dir: Optional[Path] = None
    ):
        super().__init__(agent_id, config or {})
        self.output_dir = output_dir or Path("./output/final")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.ffmpeg = FFmpegProcessor()
        self.logger = logging.getLogger(__name__)

    async def execute(
        self,
        video_results: List[Dict[str, Any]],
        output_filename: str = "final_drama.mp4",
        bgm_path: Optional[str] = None,
        add_subtitles: bool = False,
        progress_callback: Optional[ProgressCallback] = None
    ) -> str:
        """
        执行视频合成

        实际的 moviepy/ffmpeg 工作在专用线程池中完成，以免阻塞事件循环。

        Args:
            video_results: 视频片段结果列表
            output_filename: 输出文件名
            bgm_path: 背景音乐路径（可选）
            add_subtitles: 是否添加字幕
            progress_callback: 合成进度回调（0-100），可安全地从工作线程触发

        Returns:
            最终视频路径
        """
        # 先做筛选，再校验文件：失败的场景 video_path 为 None，若先校验整体会让
        # “跳过失败场景、用成功片段合成”的容错逻辑形同虚设。
        successful_videos = self._select_composable_clips(video_results)
        failed_videos = [v for v in video_results if not v.get('success', False)]

        if failed_videos:
            failed_ids = ', '.join([v.get('scene_id', 'unknown') for v in failed_videos])
            self.logger.warning(
                f"Composing video with {len(successful_videos)} successful scenes. "
                f"Skipping {len(failed_videos)} failed scenes: {failed_ids}"
            )

        if not successful_videos:
            error = ValueError("No successful video clips to compose")
            await self.on_error(error)
            raise error

        if not await self.validate_input(successful_videos):
            raise ValueError("Invalid video results")

        # 按scene_id排序
        successful_videos = sorted(successful_videos, key=lambda x: x['scene_id'])

        self.logger.info(f"Starting video composition with {len(successful_videos)} clips")

        reporter, pending = self._make_thread_progress_reporter(progress_callback)

        try:
            output_path = await run_media_blocking(
                self._compose_sync,
                successful_videos,
                output_filename,
                bgm_path,
                add_subtitles,
                reporter,
            )
        except Exception as e:
            await self._drain(pending)
            await self.on_error(e)
            raise

        # 合成结束前已排入事件循环的进度回调必须执行完，否则它们可能在
        # 95%/100% 之后才落地，把任务进度写回更小的值。
        await self._drain(pending)

        self.logger.info(f"Video composition completed: {output_path}")

        await self.on_complete(output_path)
        return output_path

    def _select_composable_clips(self, video_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """挑出可参与合成的片段（成功且文件存在），缺失文件只告警跳过"""
        selected: List[Dict[str, Any]] = []

        for result in video_results:
            if not result.get('success', False):
                continue

            video_path = result.get('video_path')
            if not video_path:
                self.logger.warning(
                    f"Skipping scene {result.get('scene_id', 'unknown')}: "
                    f"no video_path although it was marked successful"
                )
                continue

            if not Path(video_path).exists():
                self.logger.warning(
                    f"Skipping scene {result.get('scene_id', 'unknown')}: "
                    f"video file is missing ({video_path})"
                )
                continue

            selected.append(result)

        return selected

    async def validate_input(self, video_results: List[Dict[str, Any]]) -> bool:
        """验证输入数据"""
        if not video_results:
            return False

        # 检查所有视频文件是否存在
        for result in video_results:
            video_path = result.get('video_path')
            if not video_path or not Path(video_path).exists():
                self.logger.error(f"Video file not found: {video_path}")
                return False

        return True

    # ------------------------------------------------------------------
    # Blocking (worker-thread) implementation
    # ------------------------------------------------------------------

    def _compose_sync(
        self,
        video_results: List[Dict[str, Any]],
        output_filename: str,
        bgm_path: Optional[str],
        add_subtitles: bool,
        report_progress: Optional[Callable[[float, str], None]] = None
    ) -> str:
        """同步完成整个合成流程（只允许在 worker 线程中调用）"""
        final_clip: Optional[VideoFileClip] = None
        closeables: List[Any] = []

        try:
            # 加载视频片段
            clips = self._load_video_clips(video_results)
            closeables.extend(clips)

            # 添加转场效果
            if self.config.get('add_transitions', False):
                clips = self._add_transitions(clips)

            # 拼接视频
            final_clip = concatenate_videoclips(clips, method="compose")
            closeables.append(final_clip)

            # 添加背景音乐
            if bgm_path:
                final_clip = self._add_background_music(final_clip, bgm_path, closeables)
                closeables.append(final_clip)

            # 添加字幕
            if add_subtitles:
                final_clip = self._add_subtitles(final_clip, video_results, closeables)
                closeables.append(final_clip)

            # 输出最终视频
            output_path = self.output_dir / output_filename
            write_kwargs: Dict[str, Any] = {
                'codec': 'libx264',
                'audio_codec': 'aac',
                'fps': self.config.get('fps', 30),
                'preset': self.config.get('preset', 'medium'),
                'threads': self.config.get('threads', 4),
            }
            logger = self._build_proglog_logger(report_progress)
            if logger is not None:
                write_kwargs['logger'] = logger

            final_clip.write_videofile(str(output_path), **write_kwargs)

            return str(output_path)

        finally:
            self._close_all(closeables)

    @staticmethod
    def _close_all(closeables: List[Any]) -> None:
        """按逆序关闭所有 moviepy 资源（同一个对象只关一次）"""
        closed: List[Any] = []
        for clip in reversed(closeables):
            if clip is None or any(clip is seen for seen in closed):
                continue
            closed.append(clip)
            try:
                clip.close()
            except Exception:  # pragma: no cover - best effort cleanup
                pass

    def _make_thread_progress_reporter(
        self,
        progress_callback: Optional[ProgressCallback]
    ) -> tuple:
        """把进度回调包装成可从 worker 线程安全调用的函数

        Returns:
            (report, pending)：report 供 worker 线程调用，pending 收集已排入
            事件循环的 future，供 ``execute`` 在返回前 drain。
        """
        if progress_callback is None:
            return None, []

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # pragma: no cover - execute() always runs in a loop
            loop = None

        pending: List[Any] = []
        is_coroutine_callback = asyncio.iscoroutinefunction(progress_callback)
        last_reported = [-1.0]

        def report(percent: float, message: str) -> None:
            try:
                # 同一个整数百分比只上报一次，避免灌满事件循环
                step = int(percent)
                if step <= last_reported[0]:
                    return
                last_reported[0] = step

                if is_coroutine_callback:
                    if loop is None:
                        return
                    future = asyncio.run_coroutine_threadsafe(
                        progress_callback(percent, message), loop
                    )
                    pending.append(future)
                else:
                    progress_callback(percent, message)
            except Exception as exc:  # pragma: no cover - never break composition
                self.logger.debug(f"Compose progress callback failed: {exc}")

        return report, pending

    async def _drain(self, pending: List[Any]) -> None:
        """等待已排入事件循环的进度回调执行完毕（忽略回调自身异常）"""
        if not pending:
            return
        futures = list(pending)
        pending.clear()
        await asyncio.gather(
            *(asyncio.wrap_future(future) for future in futures),
            return_exceptions=True,
        )

    def _build_proglog_logger(
        self,
        report_progress: Optional[Callable[[float, str], None]]
    ):
        """用 proglog 把 moviepy 的写片进度转成 0-100 的进度回调"""
        if report_progress is None:
            return None

        try:
            import proglog
        except Exception:  # pragma: no cover - proglog ships with moviepy
            return None

        agent_logger = self.logger
        min_interval = float(self.config.get('progress_min_interval', 0.5) or 0.0)

        class _ProgressLogger(proglog.ProgressBarLogger):
            def __init__(self):
                # logged_bars=None: 不要往 stdout 打印 ANSI 进度条（后端日志会被污染）
                super().__init__(logged_bars=None, min_time_interval=min_interval)

            def bars_callback(self, bar, attr, value, old_value=None):
                try:
                    if attr != 'index' or bar not in _PROGRESS_BARS:
                        return
                    total = self.bars.get(bar, {}).get('total') or 0
                    if total <= 0:
                        return
                    percent = min(max(value / total, 0.0), 1.0) * 100.0
                    report_progress(percent, f"Composing final video... {int(percent)}%")
                except Exception as exc:  # pragma: no cover - logging only
                    agent_logger.debug(f"Compose progress bar failed: {exc}")

        return _ProgressLogger()

    def _load_video_clips(self, video_results: List[Dict[str, Any]]) -> List[VideoFileClip]:
        """加载视频片段"""
        clips = []

        for result in video_results:
            video_path = result['video_path']
            self.logger.info(f"Loading clip: {video_path}")

            clip = VideoFileClip(video_path)
            clips.append(clip)

        return clips

    def _add_transitions(self, clips: List[VideoFileClip]) -> List[VideoFileClip]:
        """
        添加转场效果

        支持的转场类型：
        - fade: 淡入淡出
        - crossfade: 交叉淡化
        """
        transition_type = self.config.get('transition_type', 'fade')
        transition_duration = self.config.get('transition_duration', 0.5)

        if transition_type == 'crossfade':
            return self._apply_crossfade(clips, transition_duration)
        elif transition_type == 'fade':
            return self._apply_fade(clips, transition_duration)
        else:
            return clips

    def _apply_fade(
        self,
        clips: List[VideoFileClip],
        duration: float
    ) -> List[VideoFileClip]:
        """应用淡入淡出效果"""
        processed = []

        for clip in clips:
            # 添加淡入淡出
            clip = clip.with_effects([FadeIn(duration), FadeOut(duration)])
            processed.append(clip)

        return processed

    def _apply_crossfade(
        self,
        clips: List[VideoFileClip],
        duration: float
    ) -> List[VideoFileClip]:
        """应用交叉淡化效果"""
        if len(clips) <= 1:
            return clips

        processed = [clips[0].with_effects([FadeIn(duration)])]

        for i in range(1, len(clips)):
            # 当前片段淡入，前一片段会淡出
            clip = clips[i].with_effects([FadeIn(duration)])
            processed.append(clip)

        processed[-1] = processed[-1].with_effects([FadeOut(duration)])

        return processed

    def _add_background_music(
        self,
        video_clip: VideoFileClip,
        bgm_path: str,
        closeables: Optional[List[Any]] = None
    ) -> VideoFileClip:
        """
        添加背景音乐（moviepy 2.x API）

        Args:
            video_clip: 视频片段
            bgm_path: 背景音乐路径
            closeables: 记录本次打开的音频资源，供调用方统一关闭

        Returns:
            添加了BGM的视频片段
        """
        self.logger.info(f"Adding background music: {bgm_path}")

        audio = None
        try:
            audio = AudioFileClip(bgm_path)
            if closeables is not None:
                closeables.append(audio)

            # 如果音乐较短，循环播放（moviepy 2.x 移除了 audio.loop()）
            if audio.duration < video_clip.duration:
                n_loops = int(video_clip.duration / audio.duration) + 1
                audio = audio.with_effects([AudioLoop(n_loops=n_loops)])
                if closeables is not None:
                    closeables.append(audio)

            # 截取到视频长度
            audio = audio.subclipped(0, video_clip.duration)
            if closeables is not None:
                closeables.append(audio)

            # 降低音量（避免盖过对话）：moviepy 2.x 用 with_volume_scaled 替代 volumex
            audio = audio.with_volume_scaled(self.config.get('bgm_volume', 0.3))
            if closeables is not None:
                closeables.append(audio)

            # 合并音频：moviepy 2.x 用 with_audio 替代 set_audio
            if video_clip.audio:
                final_audio = CompositeAudioClip([video_clip.audio, audio])
                if closeables is not None:
                    closeables.append(final_audio)
                merged = video_clip.with_audio(final_audio)
            else:
                merged = video_clip.with_audio(audio)

            if closeables is not None:
                closeables.append(merged)
            return merged

        except Exception as e:
            self.logger.error(f"Failed to add BGM: {e}")
            return video_clip

    def _add_subtitles(
        self,
        video_clip: VideoFileClip,
        video_results: List[Dict[str, Any]],
        closeables: Optional[List[Any]] = None
    ) -> VideoFileClip:
        """
        添加字幕（moviepy 2.x API）

        字幕是可选增强：失败时只记录警告，不应让整条合成失败。

        Args:
            video_clip: 视频片段
            video_results: 视频结果（包含字幕信息）
            closeables: 记录本次创建的资源，供调用方统一关闭

        Returns:
            添加了字幕的视频片段
        """
        self.logger.info("Adding subtitles")

        font = self._resolve_subtitle_font()
        font_size = self.config.get('subtitle_fontsize', 24)

        subtitle_clips: List[Any] = []
        current_time = 0.0

        try:
            for result in video_results:
                for dialogue in result.get('dialogues', []) or []:
                    text = dialogue.get('content')
                    if not text:
                        continue

                    clip = TextClip(
                        text=text,
                        font=font,
                        font_size=font_size,
                        color='white',
                        stroke_color='black',
                        stroke_width=2,
                        method='label',
                    )
                    duration = float(dialogue.get('duration', 2.0))
                    clip = clip.with_position(('center', 'bottom'))
                    clip = clip.with_start(current_time)
                    clip = clip.with_duration(duration)

                    subtitle_clips.append(clip)
                    current_time += duration

            if not subtitle_clips:
                return video_clip

            if closeables is not None:
                closeables.extend(subtitle_clips)

            # 合成字幕和视频
            composed = CompositeVideoClip([video_clip] + subtitle_clips)
            if closeables is not None:
                closeables.append(composed)
            return composed

        except Exception as e:
            self.logger.warning(f"Failed to add subtitles, continuing without them: {e}")
            self._close_all(subtitle_clips)
            return video_clip

    def _resolve_subtitle_font(self) -> Optional[str]:
        """解析字幕字体：优先使用配置的字体文件路径，否则回退到 PIL 默认字体"""
        configured = self.config.get('subtitle_font')

        if not configured:
            return None

        try:
            from PIL import ImageFont

            ImageFont.truetype(configured)
            return configured
        except Exception:
            self.logger.warning(
                f"Subtitle font '{configured}' is unavailable, using Pillow default font"
            )
            return None

    async def close(self):
        """关闭资源"""
        pass
