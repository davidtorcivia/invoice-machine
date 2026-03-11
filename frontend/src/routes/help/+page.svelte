<script>
  import Header from '$lib/components/Header.svelte';
  import CollapsibleSection from '$lib/components/CollapsibleSection.svelte';
  import { helpSections } from '$lib/help/content';

  let openSections = Object.fromEntries(helpSections.map((section, index) => [section.key, index === 0]));
</script>

<Header title="Help & Documentation" subtitle="Learn how to use Invoice Machine" />

<div class="page-content">
  <div class="help-sections">
    {#each helpSections as section}
      <CollapsibleSection title={section.title} icon={section.icon} bind:open={openSections[section.key]}>
        <div class="help-content">
          {@html section.content}
        </div>
      </CollapsibleSection>
    {/each}
  </div>
</div>

<style>
  .page-content {
    padding: var(--space-8);
    max-width: 900px;
  }

  .help-sections {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .help-content :global(h3) {
    margin: var(--space-4) 0 var(--space-2);
    font-size: 1rem;
  }

  .help-content :global(p),
  .help-content :global(ol),
  .help-content :global(ul) {
    color: var(--color-text-secondary);
    line-height: 1.6;
  }

  .help-content :global(code) {
    background: var(--color-bg-sunken);
    padding: 0.1em 0.3em;
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
  }

  .help-content :global(.note) {
    padding: var(--space-3);
    background: var(--color-bg-sunken);
    border-left: 3px solid var(--color-primary);
    border-radius: var(--radius-md);
  }

  @media (max-width: 768px) {
    .page-content {
      padding: var(--space-4);
    }
  }
</style>
