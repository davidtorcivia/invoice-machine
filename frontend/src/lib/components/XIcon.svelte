<script>
  import Icons from './Icons.svelte';
  export let size = 'md';
  export let class_ = '';
</script>

<Icons {size} class_={class_}>
  <line x1="18" y1="6" x2="6" y2="18" />
  <line x1="6" y1="6" x2="18" y2="18" />
</Icons>
