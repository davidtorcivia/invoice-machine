<script>
  import Icons from './Icons.svelte';
  export let size = 'md';
  export let class_ = '';
</script>

<Icons {size} class_={class_}>
  <line x1="12" y1="5" x2="12" y2="19" />
  <line x1="5" y1="12" x2="19" y2="12" />
</Icons>
