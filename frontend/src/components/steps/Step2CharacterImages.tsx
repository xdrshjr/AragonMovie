'use client';

import React, { useState, useEffect } from 'react';
import { Card, Button, Input, ImageGrid, LoadingAnimation } from '@/components/ui';
import { apiClient } from '@/lib/api';
import { logger } from '@/lib/logger';
import { processImageResults } from '@/lib/imageHelpers';
import { resolveActiveImageService } from '@/lib/imageService';
import { Character, APIException } from '@/lib/types';
import { VideoType, VideoSubtype, VIDEO_TYPE_DEFINITIONS } from '@/lib/types/videoTypes';
import { parseYamlScript, extractCharactersFromParsedScript } from '@/lib/yamlParser';

interface Step2CharacterImagesProps {
  polishedScript: string;
  videoType?: VideoType;
  videoSubtype?: VideoSubtype;
  onNext: (characters: Character[]) => void;
  onBack: () => void;
  initialCharacters?: Character[];
}

export const Step2CharacterImages: React.FC<Step2CharacterImagesProps> = ({
  polishedScript,
  videoType,
  videoSubtype,
  onNext,
  onBack,
  initialCharacters = [],
}) => {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [generatingFor, setGeneratingFor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);

  // Extract characters when component mounts or script changes
  useEffect(() => {
    if (initialCharacters.length > 0) {
      setCharacters(initialCharacters);
    } else {
      const extracted = extractCharactersFromScript(polishedScript);
      setCharacters(extracted);
    }
  }, [polishedScript, initialCharacters]);

  function extractCharactersFromScript(script: string): Character[] {
    logger.info('Step2CharacterImages', 'Starting character extraction', {
      scriptLength: script.length,
    });

    // Parse YAML
    const parseResult = parseYamlScript(script);
    
    if (!parseResult.success) {
      const errorMsg = `Failed to parse script: ${parseResult.error}`;
      logger.error('Step2CharacterImages', errorMsg);
      setParseError(errorMsg);
      return [];
    }

    if (!parseResult.data) {
      const errorMsg = 'No data found in parsed script';
      logger.error('Step2CharacterImages', errorMsg);
      setParseError(errorMsg);
      return [];
    }

    // Extract characters
    const extractedChars = extractCharactersFromParsedScript(parseResult.data);
    
    if (extractedChars.length === 0) {
      const errorMsg = 'No characters found in script. Please ensure your script has a "characters" section or characters defined in scenes.';
      logger.warn('Step2CharacterImages', errorMsg);
      setParseError(errorMsg);
      return [];
    }

    // Convert to Character type
    const characters = extractedChars.map(char => ({
      name: char.name,
      description: char.description,
      mode: 'generate' as const,
      imageCount: 3,
      generatedImages: [],
      selectedImage: null,
    }));

    logger.info('Step2CharacterImages', `Successfully extracted ${characters.length} characters`, {
      characters: characters.map(c => c.name),
    });

    setParseError(null);
    return characters;
  }

  const handleGenerateImages = async (characterName: string) => {
    const character = characters.find((c) => c.name === characterName);
    if (!character) {
      logger.warn('Step2CharacterImages', `Character not found: ${characterName}`);
      return;
    }

    logger.info('Step2CharacterImages', `Starting image generation for character: ${characterName}`, {
      count: character.imageCount,
      description: character.description,
    });

    setGeneratingFor(characterName);
    setError(null);

    try {
      logger.debug('Step2CharacterImages', `Creating ${character.imageCount} image generation requests for ${characterName}`);
      
      // Use the image service actually configured in the backend
      // (.env IMAGE_SERVICE_TYPE / settings center) instead of hardcoding one.
      const imageService = await resolveActiveImageService();
      logger.info(
        'Step2CharacterImages',
        `Using image service: ${imageService ?? 'backend default'}`
      );

      const imagePromises = Array.from({ length: character.imageCount }).map((_, index) => {
        logger.debug('Step2CharacterImages', `Generating image ${index + 1}/${character.imageCount} for ${characterName}`);
        // Build character reference prompt similar to CLI
        const prompt = buildCharacterReferencePrompt(character, videoType, videoSubtype);
        logger.debug('Step2CharacterImages', `Image ${index + 1} prompt`, { promptLength: prompt.length });

        return apiClient.generateImage({
          prompt,
          service: imageService,
          width: 1920,
          height: 1920,
          optimize_prompt: true,
        });
      });

      const results = await Promise.all(imagePromises);
      logger.debug('Step2CharacterImages', `Received ${results.length} raw results for ${characterName}`);
      
      // Process image URLs, handling both URL and base64 responses
      const imageUrls = processImageResults(results);
      
      if (imageUrls.length === 0) {
        logger.error('Step2CharacterImages', `No valid images generated for ${characterName}`, {
          rawResultsCount: results.length,
        });
        throw new Error('No valid images were generated. Please try again.');
      }

      setCharacters((prev) =>
        prev.map((c) =>
          c.name === characterName
            ? { ...c, generatedImages: imageUrls, selectedImage: imageUrls[0] }
            : c
        )
      );

      logger.info('Step2CharacterImages', `Successfully generated images for ${characterName}`, {
        requested: character.imageCount,
        received: imageUrls.length,
        firstImagePreview: imageUrls[0]?.substring(0, 50) + '...',
      });
    } catch (err) {
      logger.error('Step2CharacterImages', `Failed to generate images for ${characterName}`, err);
      
      if (err instanceof APIException) {
        setError(`Failed to generate images for ${characterName}: ${err.message}`);
        logger.error('Step2CharacterImages', 'API Exception details', {
          code: err.code,
          details: err.details,
          retryable: err.retryable,
        });
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('An unexpected error occurred. Please try again.');
        logger.error('Step2CharacterImages', 'Unknown error type', { error: err });
      }
    } finally {
      setGeneratingFor(null);
      logger.debug('Step2CharacterImages', `Image generation process completed for ${characterName}`);
    }
  };

  const handleImageSelect = (characterName: string, imageUrl: string) => {
    logger.debug('Step2CharacterImages', `Selecting image for character ${characterName}`, {
      imageUrlPreview: imageUrl.substring(0, 50) + '...',
    });
    
    setCharacters((prev) =>
      prev.map((c) =>
        c.name === characterName ? { ...c, selectedImage: imageUrl } : c
      )
    );
    
    logger.info('Step2CharacterImages', `Image selected for ${characterName}`);
  };

  const handleFileUpload = async (characterName: string, file: File) => {
    logger.info('Step2CharacterImages', `Starting file upload for character: ${characterName}`, {
      fileName: file.name,
      fileSize: file.size,
      fileType: file.type,
    });

    // Validate file type
    if (!file.type.startsWith('image/')) {
      const errorMsg = `Invalid file type: ${file.type}. Please upload an image file.`;
      logger.warn('Step2CharacterImages', errorMsg, { fileName: file.name });
      setError(errorMsg);
      return;
    }

    // Validate file size (max 10MB)
    const maxSize = 10 * 1024 * 1024;
    if (file.size > maxSize) {
      const errorMsg = `File too large: ${(file.size / 1024 / 1024).toFixed(2)}MB. Maximum size is 10MB.`;
      logger.warn('Step2CharacterImages', errorMsg, { fileName: file.name });
      setError(errorMsg);
      return;
    }

    setError(null);
    logger.debug('Step2CharacterImages', 'Reading file as data URL');

    const reader = new FileReader();
    
    reader.onerror = () => {
      const errorMsg = 'Failed to read file. Please try again.';
      logger.error('Step2CharacterImages', errorMsg, { fileName: file.name });
      setError(errorMsg);
    };
    
    reader.onload = () => {
      const dataUrl = reader.result as string;
      logger.debug('Step2CharacterImages', 'File read successfully', {
        dataUrlLength: dataUrl.length,
        dataUrlPreview: dataUrl.substring(0, 50) + '...',
      });
      
      setCharacters((prev) =>
        prev.map((c) =>
          c.name === characterName
            ? {
                ...c,
                generatedImages: [dataUrl, ...c.generatedImages],
                selectedImage: dataUrl,
              }
            : c
        )
      );
      
      logger.info('Step2CharacterImages', `Successfully uploaded image for ${characterName}`, {
        fileName: file.name,
      });
    };
    
    reader.readAsDataURL(file);
  };

  const handleNext = () => {
    logger.debug('Step2CharacterImages', 'Validating character images before proceeding');
    
    const missingCharacters = characters.filter((c) => !c.selectedImage);
    
    if (missingCharacters.length > 0) {
      const errorMsg = `Please select or generate images for: ${missingCharacters.map((c) => c.name).join(', ')}`;
      logger.warn('Step2CharacterImages', errorMsg, {
        missingCount: missingCharacters.length,
        missingCharacters: missingCharacters.map(c => c.name),
      });
      setError(errorMsg);
      return;
    }

    const charactersSummary = characters.map(c => ({
      name: c.name,
      hasImage: !!c.selectedImage,
      totalImages: c.generatedImages.length,
      mode: c.mode,
    }));

    logger.info('Step2CharacterImages', 'Proceeding to scene images step', {
      totalCharacters: characters.length,
      charactersSummary,
    });
    
    onNext(characters);
  };

  return (
    <div className="space-y-6">
      <Card>
        <div className="space-y-3">
          <h3 className="text-lg font-semibold text-text-primary">Character Reference Images</h3>
          <p className="text-apple-body text-text-secondary">
            For each character, you can either generate reference images using AI or upload your
            own. Select the best image for each character to ensure consistency throughout the
            video.
          </p>
          <div className="flex items-center gap-2 text-sm text-text-secondary">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
            </svg>
            <span>Found {characters.length} character{characters.length !== 1 ? 's' : ''} in your script</span>
          </div>
          
          {/* Parse Error Display */}
          {parseError && (
            <div className="mt-4 p-4 bg-warning-soft border border-warning-border rounded-apple-md">
              <div className="flex items-start gap-3">
                <svg className="w-5 h-5 text-warning-text flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
                <div className="flex-1">
                  <h4 className="text-sm font-semibold text-warning-text mb-1">
                    Script Parsing Issue
                  </h4>
                  <p className="text-sm text-warning-text">{parseError}</p>
                  <button
                    onClick={() => {
                      logger.info('Step2CharacterImages', 'User clicked to view script in console');
                      console.log('=== SCRIPT CONTENT ===');
                      console.log(polishedScript);
                      console.log('=== END SCRIPT ===');
                    }}
                    className="mt-2 text-xs text-warning-text underline hover:no-underline"
                  >
                    Click to log script to browser console for debugging
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </Card>

      {/* No Characters Found Warning */}
      {characters.length === 0 && (
        <Card>
          <div className="text-center py-8">
            <svg className="w-16 h-16 mx-auto text-text-tertiary mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
            <h3 className="text-lg font-semibold text-text-primary mb-2">No Characters Found</h3>
            <p className="text-text-secondary mb-4">
              Your script doesn't seem to have any characters defined. Please go back and ensure your script includes:
            </p>
            <ul className="text-left max-w-md mx-auto space-y-2 text-sm text-text-secondary mb-6">
              <li className="flex items-start gap-2">
                <span className="text-accent">•</span>
                <span>A <code className="px-1 py-0.5 bg-surface-hover rounded text-xs">characters:</code> section with character definitions</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-accent">•</span>
                <span>Or characters mentioned in scene dialogues</span>
              </li>
            </ul>
            <Button onClick={onBack} variant="secondary">
              <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
              Back to Edit Script
            </Button>
          </div>
        </Card>
      )}

      {/* Character Cards */}
      <div className="space-y-6">
        {characters.map((character) => (
          <Card key={character.name} title={character.name}>
            <div className="space-y-4">
              {/* Character Description */}
              <div className="bg-surface-hover p-3 rounded-apple-sm">
                <p className="text-sm text-text-secondary">{character.description}</p>
              </div>

              {/* Mode Selection */}
              <div className="flex gap-4">
                <Button
                  variant={character.mode === 'generate' ? 'primary' : 'secondary'}
                  size="sm"
                  onClick={() => {
                    logger.debug('Step2CharacterImages', `Switching to generate mode for ${character.name}`);
                    setCharacters((prev) =>
                      prev.map((c) =>
                        c.name === character.name ? { ...c, mode: 'generate' } : c
                      )
                    );
                  }}
                >
                  <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  Auto Generate
                </Button>
                <Button
                  variant={character.mode === 'upload' ? 'primary' : 'secondary'}
                  size="sm"
                  onClick={() => {
                    logger.debug('Step2CharacterImages', `Switching to upload mode for ${character.name}`);
                    setCharacters((prev) =>
                      prev.map((c) =>
                        c.name === character.name ? { ...c, mode: 'upload' } : c
                      )
                    );
                  }}
                >
                  <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  Manual Upload
                </Button>
              </div>

              {/* Generate Mode */}
              {character.mode === 'generate' && (
                <div className="space-y-3">
                  <div className="flex gap-4 items-end">
                    <Input
                      label="Number of Images"
                      type="number"
                      min="1"
                      max="5"
                      value={character.imageCount}
                      onChange={(e) => {
                        const newCount = parseInt(e.target.value, 10);
                        logger.debug('Step2CharacterImages', `Changing image count for ${character.name}`, {
                          oldCount: character.imageCount,
                          newCount,
                        });
                        setCharacters((prev) =>
                          prev.map((c) =>
                            c.name === character.name
                              ? { ...c, imageCount: newCount }
                              : c
                          )
                        );
                      }}
                      className="w-32"
                      helperText="Generate 1-5 variations"
                    />
                    <Button
                      onClick={() => handleGenerateImages(character.name)}
                      loading={generatingFor === character.name}
                      loadingText="Generating..."
                      disabled={generatingFor !== null}
                      size="md"
                    >
                      <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                      </svg>
                      Generate Images
                    </Button>
                  </div>
                  {character.generatedImages.length === 0 && (
                    <p className="text-sm text-text-secondary italic">
                      Click "Generate Images" to create AI-generated character reference images
                    </p>
                  )}
                </div>
              )}

              {/* Upload Mode */}
              {character.mode === 'upload' && (
                <div className="space-y-3">
                  <div className="flex items-center gap-4">
                    <label className="flex-1">
                      <input
                        type="file"
                        accept="image/*"
                        className="hidden"
                        id={`upload-${character.name}`}
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) {
                            handleFileUpload(character.name, file);
                          }
                          // Reset input value to allow re-uploading the same file
                          e.target.value = '';
                        }}
                      />
                      <Button
                        as="span"
                        variant="secondary"
                        size="md"
                        className="cursor-pointer w-full sm:w-auto"
                      >
                        <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                        </svg>
                        Choose Image File
                      </Button>
                    </label>
                  </div>
                  <div className="text-sm text-text-secondary space-y-1">
                    <p className="flex items-center gap-2">
                      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                      </svg>
                      Supported formats: JPG, PNG, WebP
                    </p>
                    <p className="flex items-center gap-2">
                      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                      </svg>
                      Maximum file size: 10MB
                    </p>
                  </div>
                  {character.generatedImages.length === 0 && (
                    <p className="text-sm text-text-secondary italic">
                      Click "Choose Image File" to upload a character reference image from your device
                    </p>
                  )}
                </div>
              )}

              {/* Loading State */}
              {generatingFor === character.name && (
                <LoadingAnimation message={`Generating ${character.imageCount} character reference image${character.imageCount > 1 ? 's' : ''}...`} />
              )}

              {/* Image Grid */}
              {character.generatedImages.length > 0 && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="text-sm font-medium text-text-primary">
                      Generated Images ({character.generatedImages.length})
                    </h4>
                    {character.selectedImage && (
                      <span className="text-xs text-success-text flex items-center gap-1">
                        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                        </svg>
                        Image selected
                      </span>
                    )}
                  </div>
                  <ImageGrid
                    label={`${character.name} 的角色参考图候选`}
                    testIdPrefix={`character-${character.name}-option`}
                    images={character.generatedImages.map((url, i) => ({
                      id: url,
                      url,
                      selected: url === character.selectedImage,
                      label: `${character.name} 候选图 ${i + 1}`,
                    }))}
                    onSelect={(imageUrl) => handleImageSelect(character.name, imageUrl)}
                    columns={3}
                    aspectRatio="1/1"
                  />
                  <p className="text-xs text-text-secondary italic">
                    Click on an image to select it as the reference for this character
                  </p>
                </div>
              )}
            </div>
          </Card>
        ))}
      </div>

      {/* Error Display */}
      {error && (
        <div className="bg-error-soft border border-error-border rounded-apple-md p-4">
          <div className="flex items-start gap-3">
            <svg className="w-5 h-5 text-error-text flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
            <div className="flex-1">
              <p className="text-error-text text-sm font-medium">Error</p>
              <p className="text-error-text text-sm mt-1">{error}</p>
            </div>
            <button
              onClick={() => setError(null)}
              className="text-error-text hover:text-white"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* Navigation */}
      <div className="flex justify-between pt-4">
        <Button 
          onClick={() => {
            logger.info('Step2CharacterImages', 'User clicked Back button');
            onBack();
          }} 
          variant="secondary" 
          size="lg"
        >
          ← Back
        </Button>
        <Button 
          onClick={handleNext} 
          size="lg"
          disabled={characters.some(c => !c.selectedImage)}
        >
          Next: Scene Images →
        </Button>
      </div>
    </div>
  );
};

/**
 * Build character reference prompt similar to CLI implementation
 * Based on agents/character_reference_agent.py
 */
function buildCharacterReferencePrompt(
  character: Character,
  videoType?: VideoType,
  videoSubtype?: VideoSubtype
): string {
  const promptParts: string[] = [];

  // Get style keywords based on video type
  let styleKeywords: string[];

  if (videoType && videoSubtype && VIDEO_TYPE_DEFINITIONS[videoType]) {
    const subtypeDef = VIDEO_TYPE_DEFINITIONS[videoType].subtypes[videoSubtype];
    if (subtypeDef) {
      styleKeywords = subtypeDef.styleKeywords;
      logger.info('Step2CharacterImages', `Using video type style for character`, {
        videoType,
        videoSubtype,
        styleKeywords,
      });
    } else {
      // Fallback to photorealistic
      styleKeywords = [
        'photorealistic', 'realistic photography', 'real person',
        'cinematic lighting', 'professional photography',
        'highly detailed', 'natural skin texture', 'realistic features'
      ];
    }
  } else {
    // Default to photorealistic style
    styleKeywords = [
      'photorealistic', 'realistic photography', 'real person',
      'cinematic lighting', 'professional photography',
      'highly detailed', 'natural skin texture', 'realistic features'
    ];
  }

  // Add style keywords
  promptParts.push(styleKeywords.join(', '));

  // Character name
  promptParts.push(character.name);

  // Extract age and gender from description if available
  const ageMatch = character.description.match(/Age:\s*(\d+)/i);
  const genderMatch = character.description.match(/Gender:\s*(male|female)/i);
  
  if (ageMatch && genderMatch) {
    const age = parseInt(ageMatch[1]);
    const gender = genderMatch[1];
    const ageDescriptor = getAgeDescriptor(age);
    promptParts.push(`${ageDescriptor} ${age}-year-old ${gender}`);
  } else if (genderMatch) {
    promptParts.push(genderMatch[1]);
  }

  // Appearance details
  const appearanceMatch = character.description.match(/Appearance:\s*([^.,]+)/i);
  if (appearanceMatch) {
    promptParts.push(appearanceMatch[1].trim());
  } else {
    // Use full description as fallback (but clean it up)
    const cleanDesc = character.description
      .replace(/Age:\s*\d+,?\s*/gi, '')
      .replace(/Gender:\s*(male|female),?\s*/gi, '')
      .trim();
    if (cleanDesc) {
      promptParts.push(cleanDesc);
    }
  }

  // Consistency keywords - matching CLI
  promptParts.push(
    'character reference sheet',
    'multiple angles',
    'front view',
    'consistent character design',
    'professional character reference',
    'high detail',
    'clear features',
    '8k quality'
  );

  return promptParts.join(', ');
}

/**
 * Get age descriptor based on age number
 * Matching CLI implementation in character_reference_agent.py
 */
function getAgeDescriptor(age: number): string {
  if (age < 13) return 'young child';
  if (age < 20) return 'teenage';
  if (age < 30) return 'young adult';
  if (age < 50) return 'middle-aged';
  if (age < 70) return 'mature';
  return 'elderly';
}

export default Step2CharacterImages;

