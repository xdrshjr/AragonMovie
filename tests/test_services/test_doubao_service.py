"""Tests for Doubao service"""
import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from services.doubao_service import DoubaoService


class TestDoubaoService:
    """测试豆包服务"""

    @pytest.fixture
    def mock_response(self):
        """模拟豆包API响应"""
        return {
            "data": [
                {
                    "url": "https://example.com/generated_image.png"
                }
            ]
        }

    @pytest.fixture
    def service(self):
        """创建测试服务实例"""
        return DoubaoService(
            api_key="test_key",
            base_url="https://test.api.com",
            endpoint="/api/v3/images/generations",
            model="doubao-seedream-4-5-251128"
        )

    @pytest.mark.asyncio
    async def test_normalize_response(self, service, mock_response):
        """测试响应标准化"""
        normalized = service._normalize_image_response(mock_response)

        assert 'image_url' in normalized
        assert normalized['image_url'] == "https://example.com/generated_image.png"
        assert 'raw_response' in normalized

    @pytest.mark.asyncio
    async def test_generate_image_text_to_image(self, service, mock_response):
        """测试文生图"""
        with patch.object(service.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.text = '{"data": [{"url": "https://example.com/image.png"}]}'
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status = MagicMock()
            mock_response_obj.headers = {}
            mock_post.return_value = mock_response_obj

            result = await service.generate_image(
                prompt="a beautiful landscape",
                width=1920,
                height=1080
            )

            assert 'image_url' in result
            assert result['image_url'] == "https://example.com/generated_image.png"

            # 验证请求payload
            call_args = mock_post.call_args
            payload = call_args.kwargs['json']
            assert payload['prompt'] == "a beautiful landscape"
            assert payload['model'] == "doubao-seedream-4-5-251128"
            assert 'image' not in payload  # 文生图不应有image字段

    @pytest.mark.asyncio
    async def test_generate_image_image_to_image(self, service, mock_response):
        """测试图生图"""
        with patch.object(service.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.text = '{"data": [{"url": "https://example.com/image.png"}]}'
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status = MagicMock()
            mock_response_obj.headers = {}
            mock_post.return_value = mock_response_obj

            # Mock image URL to base64 conversion
            with patch.object(service, '_image_url_to_base64', new_callable=AsyncMock) as mock_convert:
                mock_convert.return_value = "base64_encoded_image_data"

                result = await service.generate_image(
                    prompt="change the background to forest",
                    width=1920,
                    height=1080,
                    reference_image="https://example.com/reference.png",
                    reference_image_weight=0.7
                )

                assert 'image_url' in result
                assert result['image_url'] == "https://example.com/generated_image.png"

                # 验证请求payload包含image字段
                call_args = mock_post.call_args
                payload = call_args.kwargs['json']
                assert 'image' in payload  # 图生图应有image字段
                assert 'base64' in payload['image'] or payload['image'].startswith('data:')

    @pytest.mark.asyncio
    async def test_generate_and_save(self, service, mock_response, tmp_path):
        """测试生成并保存"""
        save_path = tmp_path / "test_image.png"

        with patch.object(service, 'generate_image', new_callable=AsyncMock) as mock_gen, \
             patch.object(service, 'download_image', new_callable=AsyncMock) as mock_download:

            mock_gen.return_value = {'image_url': 'https://example.com/image.png'}
            mock_download.return_value = save_path

            result = await service.generate_and_save(
                prompt="test prompt",
                save_path=save_path
            )

            assert result['image_path'] == str(save_path)
            assert result['prompt'] == "test prompt"
            mock_gen.assert_called_once()
            mock_download.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_local_image_as_base64(self, service, tmp_path):
        """测试读取本地图片为base64"""
        # 创建测试图片
        test_image = tmp_path / "test.png"
        test_image.write_bytes(b"fake image data")

        base64_data = await service._read_image_as_base64(test_image)

        assert base64_data is not None
        assert len(base64_data) > 0

    @pytest.mark.asyncio
    async def test_service_close(self, service):
        """测试服务关闭"""
        with patch.object(service.client, 'aclose', new_callable=AsyncMock) as mock_close:
            await service.close()
            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_with_seed_and_cfg(self, service, mock_response):
        """测试带seed和cfg参数的生成"""
        with patch.object(service.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.text = '{"data": [{"url": "https://example.com/image.png"}]}'
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status = MagicMock()
            mock_response_obj.headers = {}
            mock_post.return_value = mock_response_obj

            result = await service.generate_image(
                prompt="test prompt",
                seed=12345,
                cfg_scale=8.0,
                steps=50
            )

            # seed / cfg_scale / steps 是「被接受但不下发」的参数：豆包(Ark)
            # 图像接口不支持它们，服务层显式忽略并只记 debug 日志（见
            # services/doubao_service.py）。这里锁定该契约，避免再次误判。
            call_args = mock_post.call_args
            payload = call_args.kwargs['json']
            assert 'seed' not in payload
            assert 'cfg_scale' not in payload
            assert 'steps' not in payload
            # 真正会下发的字段仍然存在
            assert payload['model'] == service.model
            assert payload['prompt'] == "test prompt"
            assert result is not None


class TestDoubaoImageToImage:
    """测试豆包图生图功能"""

    @pytest.fixture
    def service(self):
        """创建测试服务实例"""
        return DoubaoService(
            api_key="test_key",
            base_url="https://test.api.com",
            model="doubao-seedream-4-5-251128"
        )

    @pytest.mark.asyncio
    async def test_image_to_image_with_local_file(self, service, tmp_path):
        """测试使用本地文件进行图生图"""
        # 创建测试图片
        test_image = tmp_path / "reference.png"
        test_image.write_bytes(b"fake image data")

        mock_response = {
            "data": [{"url": "https://example.com/generated.png"}]
        }

        with patch.object(service.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.text = '{"data": [{"url": "https://example.com/generated.png"}]}'
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status = MagicMock()
            mock_response_obj.headers = {}
            mock_post.return_value = mock_response_obj

            result = await service.generate_image(
                prompt="change style",
                reference_image=str(test_image)
            )

            assert 'image_url' in result

            # 验证image字段存在
            call_args = mock_post.call_args
            payload = call_args.kwargs['json']
            assert 'image' in payload

    @pytest.mark.asyncio
    async def test_image_to_image_with_url(self, service):
        """测试使用URL进行图生图"""
        mock_response = {
            "data": [{"url": "https://example.com/generated.png"}]
        }

        with patch.object(service.client, 'post', new_callable=AsyncMock) as mock_post, \
             patch.object(service, '_image_url_to_base64', new_callable=AsyncMock) as mock_convert:

            mock_convert.return_value = "base64_data"

            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.text = '{"data": [{"url": "https://example.com/generated.png"}]}'
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status = MagicMock()
            mock_response_obj.headers = {}
            mock_post.return_value = mock_response_obj

            result = await service.generate_image(
                prompt="change style",
                reference_image="https://example.com/reference.png"
            )

            assert 'image_url' in result
            mock_convert.assert_called_once()
