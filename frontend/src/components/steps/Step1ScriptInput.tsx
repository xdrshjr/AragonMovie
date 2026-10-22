'use client';

import React, { useState, useEffect } from 'react';
import { Card, Button, Textarea, Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui';
import ScriptConfiguration from '@/components/ScriptConfiguration';
import { apiClient } from '@/lib/api';
import { logger } from '@/lib/logger';
import { APIException } from '@/lib/types';
import { VideoType, VideoSubtype, getVideoTypeDisplayName, getSubtypeDisplayName } from '@/lib/types/videoTypes';
import { getScriptPrompts } from '@/lib/scriptPrompts';
import { validateYAMLScript, getSampleYAMLScript } from '@/lib/yamlValidator';
import {
  ScriptGenerationConfig,
  DEFAULT_SCRIPT_CONFIG,
} from '@/lib/types/scriptConfig';

interface Step1ScriptInputProps {
  onNext: (userScript: string, polishedScript: string) => void;
  onBack?: () => void;
  initialUserScript?: string;
  initialPolishedScript?: string;
  videoType?: VideoType;
  videoSubtype?: VideoSubtype;
}

type ScriptMode = 'polish' | 'direct';

export const Step1ScriptInput: React.FC<Step1ScriptInputProps> = ({
  onNext,
  onBack,
  initialUserScript = '',
  initialPolishedScript = '',
  videoType,
  videoSubtype,
}) => {
  // Mode state - default to 'polish', will load from localStorage after mount
  const [mode, setMode] = useState<ScriptMode>('polish');
  const [isMounted, setIsMounted] = useState(false);

  // Polish mode state
  const [userScript, setUserScript] = useState(initialUserScript);
  const [polishedScript, setPolishedScript] = useState(initialPolishedScript);
  const [isPolishing, setIsPolishing] = useState(false);

  // Configuration state
  const [config, setConfig] = useState<ScriptGenerationConfig>({
    ...DEFAULT_SCRIPT_CONFIG,
    videoType,
    videoSubtype,
  });
  const [configValid, setConfigValid] = useState(true);
  const [configErrors, setConfigErrors] = useState<string[]>([]);
  const [showConfig, setShowConfig] = useState(true);

  // Direct mode state
  const [directScript, setDirectScript] = useState(initialPolishedScript || '');

  // Common state
  const [error, setError] = useState<string | null>(null);
  const [validationWarnings, setValidationWarnings] = useState<string[]>([]);
  const [showSample, setShowSample] = useState(false);

  // Load mode preference from localStorage after mount (to avoid hydration mismatch)
  useEffect(() => {
    setIsMounted(true);
    const savedMode = localStorage.getItem('scriptInputMode');
    if (savedMode === 'direct' || savedMode === 'polish') {
      setMode(savedMode);
      logger.debug('Step1ScriptInput', 'Loaded saved mode preference', { mode: savedMode });
    }

    // Load saved configuration
    const savedConfig = localStorage.getItem('scriptGenerationConfig');
    if (savedConfig) {
      try {
        const parsedConfig = JSON.parse(savedConfig);
        // Merge saved config with video type from props (props take precedence)
        setConfig({
          ...parsedConfig,
          videoType,
          videoSubtype,
        });
        logger.debug('Step1ScriptInput', 'Loaded saved configuration with video type override', {
          config: parsedConfig,
          videoType,
          videoSubtype,
        });
      } catch (e) {
        logger.warn('Step1ScriptInput', 'Failed to parse saved configuration', e);
      }
    }
  }, [videoType, videoSubtype]);

  // Save mode preference to localStorage when it changes
  useEffect(() => {
    if (isMounted) {
      localStorage.setItem('scriptInputMode', mode);
      logger.debug('Step1ScriptInput', 'Script input mode changed', { mode });
    }
  }, [mode, isMounted]);

  // Save configuration to localStorage when it changes
  useEffect(() => {
    if (isMounted) {
      localStorage.setItem('scriptGenerationConfig', JSON.stringify(config));
      logger.debug('Step1ScriptInput', 'Configuration saved', { config });
    }
  }, [config, isMounted]);

  // Handle configuration validation
  const handleConfigValidationChange = (isValid: boolean, errors: string[]) => {
    setConfigValid(isValid);
    setConfigErrors(errors);
  };

  // Handle mode change with unsaved content warning
  const handleModeChange = (newMode: string) => {
    const newModeValue = newMode as ScriptMode;

    if (mode === 'polish' && userScript.trim() && !polishedScript.trim()) {
      const confirmed = window.confirm(
        'You have unpolished script content. Switching modes will keep your work. Continue?'
      );
      if (!confirmed) {
        logger.info('Step1ScriptInput', 'User cancelled mode switch');
        return;
      }
    }

    if (mode === 'direct' && directScript.trim() && newModeValue === 'polish') {
      const confirmed = window.confirm(
        'You have direct script content. Switching to polish mode will preserve it. Continue?'
      );
      if (!confirmed) {
        logger.info('Step1ScriptInput', 'User cancelled mode switch');
        return;
      }
    }

    setMode(newModeValue);
    setError(null);
    setValidationWarnings([]);
    logger.info('Step1ScriptInput', 'Mode switched', { from: mode, to: newModeValue });
  };

  // Polish mode: Handle polish button click
  const handlePolish = async () => {
    if (!userScript.trim()) {
      setError('Please enter a script description');
      logger.warn('Step1ScriptInput', 'Polish attempted with empty script');
      return;
    }

    // Validate configuration
    if (!configValid) {
      setError(`Configuration errors: ${configErrors.join(', ')}`);
      logger.warn('Step1ScriptInput', 'Polish attempted with invalid configuration', { configErrors });
      return;
    }

    logger.info('Step1ScriptInput', 'User submitted script for polishing', {
      scriptLength: userScript.length,
      config,
    });
    setIsPolishing(true);
    setError(null);
    setValidationWarnings([]);

    try {
      // Get language-appropriate prompts with configuration
      const prompts = getScriptPrompts(userScript, config);

      logger.debug('Step1ScriptInput', 'Using prompts for polishing', {
        language: prompts.language,
        systemPromptLength: prompts.systemPrompt.length,
        userMessageLength: prompts.userMessage.length,
        config,
      });

      const response = await apiClient.chat({
        messages: [
          {
            role: 'system',
            content: prompts.systemPrompt,
          },
          {
            role: 'user',
            content: prompts.userMessage,
          },
        ],
        temperature: 0.7,
        max_tokens: 8192,
      });

      const polished = response.choices[0]?.message?.content || '';

      if (!polished) {
        logger.error('Step1ScriptInput', 'Empty response from LLM');
        setError('Received empty response from AI. Please try again.');
        return;
      }

      // Validate the polished YAML
      const validation = validateYAMLScript(polished);

      if (!validation.isValid) {
        logger.warn('Step1ScriptInput', 'Generated script validation failed', {
          errors: validation.errors,
          warnings: validation.warnings,
        });
        setError(
          `Generated script has validation errors: ${validation.errors.join(', ')}. Please review and edit.`
        );
        setValidationWarnings(validation.warnings);
      } else if (validation.warnings.length > 0) {
        logger.info('Step1ScriptInput', 'Generated script has warnings', {
          warnings: validation.warnings,
        });
        setValidationWarnings(validation.warnings);
      }

      setPolishedScript(polished);
      logger.info('Step1ScriptInput', 'Script polished successfully', {
        originalLength: userScript.length,
        polishedLength: polished.length,
        language: prompts.language,
        isValid: validation.isValid,
        warningCount: validation.warnings.length,
      });
    } catch (err) {
      logger.error('Step1ScriptInput', 'Failed to polish script', err);

      if (err instanceof APIException) {
        setError(`Failed to polish script: ${err.message}`);
      } else {
        setError('An unexpected error occurred. Please try again.');
      }
    } finally {
      setIsPolishing(false);
    }
  };

  // Direct mode: Handle script validation
  const handleDirectScriptChange = (value: string) => {
    setDirectScript(value);
    setError(null);
    setValidationWarnings([]);

    if (value.trim()) {
      // Debounced validation (validate after user stops typing)
      const timeoutId = setTimeout(() => {
        const validation = validateYAMLScript(value);
        
        logger.debug('Step1ScriptInput', 'Direct script validation', {
          isValid: validation.isValid,
          errorCount: validation.errors.length,
          warningCount: validation.warnings.length,
        });

        if (!validation.isValid) {
          setError(validation.errors.join('; '));
        }
        
        if (validation.warnings.length > 0) {
          setValidationWarnings(validation.warnings);
        }
      }, 500);

      return () => clearTimeout(timeoutId);
    }
  };

  // Load sample script
  const handleLoadSample = () => {
    const sample = getSampleYAMLScript();
    setDirectScript(sample);
    setError(null);
    setValidationWarnings([]);
    setShowSample(false);
    logger.info('Step1ScriptInput', 'Sample script loaded');
  };

  // Handle next button
  const handleNext = () => {
    const finalScript = mode === 'polish' ? polishedScript : directScript;

    if (!finalScript.trim()) {
      setError(
        mode === 'polish'
          ? 'Please polish the script first or switch to Direct Input mode'
          : 'Please enter a script in YAML format'
      );
      logger.warn('Step1ScriptInput', 'Next attempted with empty script', { mode });
      return;
    }

    // Final validation
    const validation = validateYAMLScript(finalScript);
    if (!validation.isValid) {
      setError(`Script validation failed: ${validation.errors.join('; ')}`);
      logger.error('Step1ScriptInput', 'Final validation failed', {
        mode,
        errors: validation.errors,
      });
      return;
    }

    logger.info('Step1ScriptInput', 'User proceeding to next step', {
      mode,
      scriptLength: finalScript.length,
      hasWarnings: validation.warnings.length > 0,
    });

    onNext(mode === 'polish' ? userScript : '', finalScript);
  };

  const finalScript = mode === 'polish' ? polishedScript : directScript;

  return (
    <div className="space-y-6">
      {/* Video Type Display Badge */}
      {videoType && videoSubtype && (
        <div className="flex items-center justify-between p-4 bg-accent-soft border border-accent-border rounded-apple-md">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <svg className="w-5 h-5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z" />
              </svg>
              <span className="font-semibold text-text-primary">
                视频类型:
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="px-3 py-1 border border-accent-border bg-accent-soft text-accent-text rounded-full text-sm font-medium">
                {getVideoTypeDisplayName(videoType, 'zh')}
              </span>
              <span className="text-text-tertiary">→</span>
              <span className="px-3 py-1 border border-accent-border bg-accent-soft text-accent-text rounded-full text-sm font-medium">
                {getSubtypeDisplayName(videoType, videoSubtype, 'zh')}
              </span>
            </div>
          </div>
          {onBack && (
            <button
              onClick={onBack}
              className="text-sm text-text-secondary hover:text-text-primary transition-colors"
            >
              ← 返回修改
            </button>
          )}
        </div>
      )}

      {/* Configuration Panel - Only show in Polish mode */}
      {mode === 'polish' && (
        <div>
          <button
            type="button"
            onClick={() => setShowConfig(!showConfig)}
            className="flex items-center gap-2 mb-4 text-accent hover:text-accent-strong transition-colors"
          >
            <svg
              className={`w-5 h-5 transition-transform ${showConfig ? 'rotate-90' : ''}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            <span className="text-apple-headline font-semibold">
              {showConfig ? '隐藏配置选项' : '显示配置选项'} / Script Configuration
            </span>
          </button>

          {showConfig && (
            <Card
              title="剧本生成配置 / Script Generation Configuration"
              subtitle="配置剧本的类型、角色、场景和内容安全选项"
            >
              <ScriptConfiguration
                config={config}
                onChange={setConfig}
                onValidationChange={handleConfigValidationChange}
              />
            </Card>
          )}

          {/* Configuration Errors */}
          {!configValid && configErrors.length > 0 && (
            <div className="mt-4 bg-error-soft border border-error-border rounded-apple-md p-4">
              <h4 className="text-sm font-semibold text-error-text mb-2">
                ⚠️ Configuration Errors:
              </h4>
              <ul className="text-sm text-error-text list-disc list-inside space-y-1">
                {configErrors.map((error, idx) => (
                  <li key={idx}>{error}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Mode Selection Tabs */}
      <Card title="Generate Script" subtitle="Choose how you want to create your video script">
        <Tabs value={mode} onValueChange={handleModeChange}>
          <TabsList>
            <TabsTrigger value="polish">
              Polish Script
            </TabsTrigger>
            <TabsTrigger value="direct">
              Direct YAML Input
            </TabsTrigger>
          </TabsList>

          {/* Polish Mode Tab */}
          <TabsContent value="polish">
            <div className="space-y-4">
              <Textarea
                label="Script Description"
                placeholder="Enter your script idea here... For example: A programmer's day - Starting in the morning at the office, working on code, having lunch with colleagues, and finally finishing a project in the evening."
                value={userScript}
                onChange={(e) => setUserScript(e.target.value)}
                rows={8}
                helperText="Provide a brief description or outline of your video script. The AI will convert it into a structured YAML format based on your configuration."
              />
              <div>
                <Button
                  onClick={handlePolish}
                  loading={isPolishing}
                  disabled={!userScript.trim() || isPolishing || !configValid}
                >
                  {isPolishing ? 'Polishing Script...' : 'Polish Script with AI'}
                </Button>
              </div>
            </div>
          </TabsContent>

          {/* Direct Input Mode Tab */}
          <TabsContent value="direct">
            <div className="space-y-4">
              <Textarea
                label="YAML Script"
                placeholder="Paste your pre-written YAML script here, or load a sample..."
                value={directScript}
                onChange={(e) => handleDirectScriptChange(e.target.value)}
                rows={16}
                helperText="Enter a complete YAML script with title, characters, and scenes. Must follow the required format."
              />
              <div className="flex gap-3">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowSample(!showSample)}
                >
                  {showSample ? 'Hide Sample' : 'Show Sample Format'}
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleLoadSample}
                >
                  Load Sample Script
                </Button>
              </div>

              {/* Sample Format Display */}
              {showSample && (
                <div className="mt-4 p-4 bg-background-deep rounded-apple-md border border-hairline">
                  <h4 className="text-apple-headline mb-2 text-text-primary">
                    Sample YAML Format:
                  </h4>
                  <div className="max-h-96 overflow-y-auto">
                    <pre className="text-apple-caption text-text-secondary overflow-x-auto">
                      <code>{getSampleYAMLScript()}</code>
                    </pre>
                  </div>
                </div>
              )}
            </div>
          </TabsContent>
        </Tabs>
      </Card>

      {/* Polished/Editable Script Section */}
      {finalScript && (
        <Card
          title={mode === 'polish' ? 'Polished Script (Editable)' : 'Script Preview'}
          subtitle="You can edit the script before proceeding"
        >
          <Textarea
            label={mode === 'polish' ? 'Polished Script (YAML)' : 'Final Script'}
            value={finalScript}
            onChange={(e) => {
              if (mode === 'polish') {
                setPolishedScript(e.target.value);
              } else {
                handleDirectScriptChange(e.target.value);
              }
            }}
            rows={12}
            helperText="Edit the YAML script as needed. Ensure proper YAML syntax (indentation, quotes, etc.)."
          />
        </Card>
      )}

      {/* Validation Warnings */}
      {validationWarnings.length > 0 && (
        <div className="bg-warning-soft border border-warning-border rounded-apple-md p-4">
          <h4 className="text-sm font-semibold text-warning-text mb-2">
            ⚠️ Warnings ({validationWarnings.length}):
          </h4>
          <div className="max-h-40 overflow-y-auto">
            <ul className="text-sm text-warning-text list-disc list-inside space-y-1 pr-2">
              {validationWarnings.map((warning, idx) => (
                <li key={idx}>{warning}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div className="bg-error-soft border border-error-border rounded-apple-md p-4">
          <p className="text-error-text text-sm font-medium">❌ {error}</p>
        </div>
      )}

      {/* Next Button */}
      <div className="flex justify-end">
        <Button
          onClick={handleNext}
          disabled={!finalScript.trim()}
          size="lg"
        >
          Next: Character Images →
        </Button>
      </div>
    </div>
  );
};

export default Step1ScriptInput;
