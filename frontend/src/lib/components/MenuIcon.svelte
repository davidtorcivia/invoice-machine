<script>
  import Icons from './Icons.svelte';
  export let size = 'md';
  export let class_ = '';
</script>

<Icons {size} class_={class_}>
  <line x1="4" y1="6" x2="20" y2="6" />
  <line x1="4" y1="12" x2="20" y2="12" />
  <line x1="4" y1="18" x2="20" y2="18" />
</Icons>
