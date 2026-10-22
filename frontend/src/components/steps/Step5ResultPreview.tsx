'use client';

import React from 'react';
import { Card, Button } from '@/components/ui';
import { logger } from '@/lib/logger';

interface Step5ResultPreviewProps {
  videoUrl: string;
  videoMetadata: {
    resolution?: string;
    duration?: number;
    size?: number;
  };
  onRegenerate: () => void;
}

export const Step5ResultPreview: React.FC<Step5ResultPreviewProps> = ({
  videoUrl,
  videoMetadata,
  onRegenerate,
}) => {
  const handleDownload = () => {
    logger.info('Step5ResultPreview', 'User downloading video', { url: videoUrl });
    
    // Create a temporary anchor element to trigger download
    const link = document.createElement('a');
    link.href = videoUrl;
    link.download = `generated-video-${Date.now()}.mp4`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleRegenerate = () => {
    logger.info('Step5ResultPreview', 'User initiated regeneration');
    onRegenerate();
  };

  return (
    <div className="space-y-6">
      {/* Success Message */}
      <Card>
        <div className="text-center py-4">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-success rounded-full mb-4 shadow-apple-glow">
            <svg
              className="w-10 h-10 text-white"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                fillRule="evenodd"
                d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                clipRule="evenodd"
              />
            </svg>
          </div>
          <h2 className="text-apple-title-2 text-text-primary mb-2">
            Video Generated Successfully!
          </h2>
          <p className="text-apple-body text-text-secondary">
            Your AI-generated video is ready to preview and download.
          </p>
        </div>
      </Card>

      {/* Video Player */}
      <Card title="Video Preview">
        <div className="aspect-video bg-black rounded-apple-md border border-hairline overflow-hidden">
          <video
            src={videoUrl}
            controls
            className="w-full h-full"
            onLoadedMetadata={() => {
              logger.info('Step5ResultPreview', 'Video preview loaded successfully');
            }}
          >
            Your browser does not support the video tag.
          </video>
        </div>
      </Card>

      {/* Video Metadata */}
      <Card title="Video Information">
        <div className="grid grid-cols-3 gap-4">
          <div className="text-center">
            <p className="text-apple-caption text-text-secondary mb-1">Resolution</p>
            <p className="text-apple-headline text-text-primary">
              {videoMetadata.resolution || '1920x1080'}
            </p>
          </div>
          <div className="text-center">
            <p className="text-apple-caption text-text-secondary mb-1">Duration</p>
            <p className="text-apple-headline text-text-primary">
              {videoMetadata.duration
                ? `${Math.round(videoMetadata.duration)}s`
                : '5s'}
            </p>
          </div>
          <div className="text-center">
            <p className="text-apple-caption text-text-secondary mb-1">Size</p>
            <p className="text-apple-headline text-text-primary">
              {videoMetadata.size
                ? `${(videoMetadata.size / (1024 * 1024)).toFixed(2)} MB`
                : 'N/A'}
            </p>
          </div>
        </div>
      </Card>

      {/* Action Buttons */}
      <div className="flex gap-4 justify-center">
        <Button onClick={handleDownload} size="lg">
          Download Video
        </Button>
        <Button onClick={handleRegenerate} variant="secondary" size="lg">
          Create Another Video
        </Button>
      </div>

      {/* Tips */}
      <Card>
        <h4 className="text-apple-headline text-text-primary mb-2">Next Steps</h4>
        <ul className="space-y-2 text-apple-body text-text-secondary">
          <li className="flex items-start gap-2">
            <span className="text-accent">•</span>
            <span>Download your video and use it in your projects</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-accent">•</span>
            <span>Click "Create Another Video" to start a new generation</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-accent">•</span>
            <span>Share your creation with others!</span>
          </li>
        </ul>
      </Card>
    </div>
  );
};

export default Step5ResultPreview;

