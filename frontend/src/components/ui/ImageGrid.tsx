import React from 'react';
import Image from 'next/image';
import { isValidImageUrl } from '@/lib/imageHelpers';

interface ImageOption {
  id: string;
  url: string;
  selected: boolean;
  /** Optional human-readable label ("候选 1", "角色正面图", ...) */
  label?: string;
}

interface ImageGridProps {
  images: ImageOption[];
  onSelect: (id: string) => void;
  columns?: number;
  aspectRatio?: string;
  /** Accessible name of the group, e.g. "角色参考图候选" */
  label?: string;
  /** data-testid prefix; each tile becomes `${testIdPrefix}-${index}` */
  testIdPrefix?: string;
}

/**
 * Selectable image grid.
 *
 * Each tile is a real <button role="option"> inside a `role="listbox"` group, so:
 * - keyboard users can Tab to a tile and activate it with Enter/Space
 * - screen readers announce the option and its selected state (aria-selected)
 * - automation can use `get_by_role('option', name=...)` or the data-testid
 *
 * The previous markup was a bare `<div onClick>` with the selection expressed
 * only through the `ring-4 ring-apple-blue` class, and the alt text was built
 * from a data-URL, which made both a11y and testing impossible.
 */
export const ImageGrid: React.FC<ImageGridProps> = ({
  images,
  onSelect,
  columns = 3,
  aspectRatio = '16/9',
  label = 'Image options',
  testIdPrefix = 'image-option',
}) => {
  const gridClasses = {
    2: 'grid-cols-2',
    3: 'grid-cols-3',
    4: 'grid-cols-4',
  }[columns] || 'grid-cols-3';

  // Filter out any invalid images
  const validImages = images.filter((img) => isValidImageUrl(img.url));

  if (validImages.length === 0) {
    return (
      <div className="p-4 text-center text-text-secondary border border-text-tertiary rounded-apple-md">
        <p>No valid images to display</p>
      </div>
    );
  }

  return (
    <div
      role="listbox"
      aria-label={label}
      className={`grid ${gridClasses} gap-4`}
      data-testid={`${testIdPrefix}-grid`}
    >
      {validImages.map((image, index) => {
        // Never derive the accessible name from the data-URL held in `id`.
        const optionLabel = image.label ?? `Image option ${index + 1}`;

        return (
          <button
            key={image.id}
            type="button"
            role="option"
            aria-selected={image.selected}
            aria-label={optionLabel}
            title={optionLabel}
            onClick={() => onSelect(image.id)}
            data-testid={`${testIdPrefix}-${index}`}
            data-selected={image.selected}
            className={`relative block w-full cursor-pointer rounded-apple-md overflow-hidden transition-apple focus:outline-none focus-visible:ring-4 focus-visible:ring-apple-blue ${
              image.selected
                ? 'ring-4 ring-apple-blue shadow-apple-lg'
                : 'ring-1 ring-text-tertiary hover:ring-2 hover:ring-apple-blue'
            }`}
            style={{ aspectRatio }}
          >
            <Image
              src={image.url}
              alt={optionLabel}
              fill
              className="object-cover"
              sizes="(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 33vw"
              unoptimized={image.url.startsWith('data:')}
            />
            {image.selected && (
              <span
                aria-hidden="true"
                className="absolute top-2 right-2 bg-apple-blue text-white rounded-full w-8 h-8 flex items-center justify-center"
              >
                <svg
                  className="w-5 h-5"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
                  <path
                    fillRule="evenodd"
                    d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                    clipRule="evenodd"
                  />
                </svg>
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
};

export default ImageGrid;
